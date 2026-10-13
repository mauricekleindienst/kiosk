"""The kiosk server: refreshes weather, news, share prices and departures in the background, serves
the screen locally and the admin interface to the local network, and updates itself at night."""

import argparse
import hashlib
import logging
import os
import threading
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from . import __version__, feeds, http_client, stock, transit, weather
from .auth import Auth
from .config import ConfigError, load_config
from .http_api import AdminHandler, ScreenHandler
from .netinfo import lan_addresses
from .schedule import is_sleeping
from .settings import SettingsStore, default_settings, load_catalog
from .store import Store
from .updates import Updater, installed_version
from .uploads import Uploads

log = logging.getLogger("kiosk")

# After a failed refresh, try again sooner than the regular interval, but do not hammer the source.
RETRY_SECONDS = 60
SCHEDULER_TICK_SECONDS = 2
# The server keeps more headlines than any widget shows; each widget applies its own limit.
HEADLINES_KEPT = 12
# Exit code after an update: systemd (Restart=always) starts the new version.
RESTART_EXIT_CODE = 3


def _utc_now():
    return datetime.now(timezone.utc)


def _key(prefix, *parts):
    return f"{prefix}-{hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:12]}"


class Kiosk:
    """Owns the configuration, the settings, the data sources and their refresh schedule."""

    def __init__(self, config, store, settings, auth, uploads,
                 fetch=http_client.fetch, fetch_json=http_client.fetch_json, clock=_utc_now, monotonic=time.monotonic):
        self.config = config
        self.store = store
        self.settings = settings
        self.auth = auth
        self.uploads = uploads
        self._fetch = fetch
        self._fetch_json = fetch_json
        self._clock = clock
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._sources = {}
        self._due = {}
        self._data_version = 0
        self._reload_token = 0
        self._screen = None
        self._started = clock()
        # Changes with every start: the screen reloads when the server restarted (after an update).
        self.build = f"{__version__}-{self._started.timestamp():.0f}"
        self.version = installed_version(__version__)
        self.admin_port = None
        self.updater = None
        self._apply(settings.get()[0])
        settings.on_change(self._apply)

    # Sources follow the settings: one for the weather at the location, one per distinct feed.

    @staticmethod
    def weather_key(settings):
        location = settings["location"]
        return _key("weather", location["lat"], location["lon"], settings["timeZone"])

    @staticmethod
    def news_key(url):
        return _key("news", url)

    @staticmethod
    def source_of(widget):
        """(key, kind, argument) of the data a widget needs, or None. Equal arguments share a key."""
        options = widget["options"]
        if widget["type"] == "news":
            return _key("news", options["url"]), "news", options["url"]
        if widget["type"] == "stock":
            return _key("stock", options["symbol"]), "stock", options["symbol"]
        if widget["type"] == "transit" and options["stop"]:
            argument = (options["stop"]["id"], tuple(options["products"]))
            return _key("transit", *argument[:1], *argument[1]), "transit", argument
        return None

    def _apply(self, settings):
        minutes = {kind: self.config[kind]["refreshMinutes"] for kind in ("weather", "news", "stock", "transit")}
        wanted = {self.weather_key(settings): ("weather", settings, minutes["weather"] * 60)}
        for widget in settings["widgets"]:
            source = self.source_of(widget)
            if source:
                key, kind, argument = source
                wanted[key] = (kind, argument, minutes[kind] * 60)
        with self._lock:
            self._sources = wanted
            self._due = {key: self._due.get(key, 0.0) for key in wanted}
        self.store.load([key for key in wanted])

    def refresh_now(self):
        with self._lock:
            self._due = {key: 0.0 for key in self._due}

    def reload_screen(self):
        with self._lock:
            self._reload_token += 1

    def _refresh_weather(self, settings, now):
        location = settings["location"]
        tz = ZoneInfo(settings["timeZone"])
        urls = weather.request_urls(self.config["weather"]["baseUrl"], location["lat"], location["lon"],
                                    settings["timeZone"], now.astimezone(tz).date())
        current = self._fetch_json(urls["current"])
        forecast = self._fetch_json(urls["forecast"])
        try:
            alerts = self._fetch_json(urls["alerts"])
        except http_client.FetchError as err:
            # Warnings are an extra; a failing alerts endpoint must not hide the forecast.
            log.warning("Weather warnings unavailable, showing the forecast without them: %s", err)
            alerts = None
        return weather.build_weather(current, forecast, alerts, now, location["name"], location["lat"], location["lon"], tz)

    def _refresh_stock(self, symbol, now):
        return stock.build_quote(self._fetch_json(stock.request_url(self.config["stock"]["baseUrl"], symbol)))

    def _refresh_transit(self, argument, now):
        stop_id, products = argument
        raw = self._fetch_json(transit.departures_url(self.config["transit"]["baseUrl"], stop_id, products))
        return transit.build_departures(raw, now)

    def search_stops(self, text):
        """Stops matching a name, for the admin's stop search."""
        return transit.build_stops(self._fetch_json(transit.locations_url(self.config["transit"]["baseUrl"], text)))

    def _refresh_news(self, url, now):
        headlines = feeds.parse_feed(self._fetch(url, accept="application/rss+xml, application/atom+xml, text/xml"))
        picked = feeds.select_headlines(headlines, now, HEADLINES_KEPT, float(self.config["news"]["maxAgeDays"]))
        return [headline.to_json() for headline in picked]

    def run_due(self, monotonic_now=None):
        """Refreshes every source whose time has come. Called by the scheduler thread and by tests."""
        monotonic_now = self._monotonic() if monotonic_now is None else monotonic_now
        with self._lock:
            due = [(key, spec) for key, spec in self._sources.items() if monotonic_now >= self._due.get(key, 0.0)]
        for key, (kind, argument, interval) in due:
            now = self._clock()
            next_due = monotonic_now + interval
            try:
                refresh = {"weather": self._refresh_weather, "news": self._refresh_news,
                           "stock": self._refresh_stock, "transit": self._refresh_transit}[kind]
                data = refresh(argument, now)
            except (http_client.FetchError, feeds.FeedError) as err:
                log.warning("Refreshing %s failed, keeping the last good data: %s", key, err)
                self.store.fail(key, str(err))
                next_due = monotonic_now + min(RETRY_SECONDS, interval)
            except Exception as err:  # noqa: BLE001 - an unexpected answer must not stop the scheduler
                log.exception("Refreshing %s failed on an unexpected answer, keeping the last good data", key)
                self.store.fail(key, str(err))
                next_due = monotonic_now + min(RETRY_SECONDS, interval)
            else:
                self.store.put(key, data, now.isoformat())
                log.info("Refreshed %s", key)
            with self._lock:
                if key in self._due:
                    self._due[key] = next_due
                self._data_version += 1

    # What the screen and the admin interface read.

    def record_screen(self, width, height):
        try:
            size = (max(0, min(int(width), 20000)), max(0, min(int(height), 20000)))
        except ValueError:
            return
        with self._lock:
            self._screen = {"width": size[0], "height": size[1], "lastSeen": self._clock().isoformat()}

    def revision(self):
        with self._lock:
            revision = {"settings": self.settings.revision, "data": self._data_version, "reload": self._reload_token}
        # The setup notice must vanish from the screen as soon as a password exists; a new build
        # (a restart after an update) makes the screen load the new files.
        return {**revision, "setup": self.auth.setup_required, "build": self.build}

    def display(self):
        """Whether the monitor should be on now, for scripts/display-power.sh on the Pi."""
        settings, _ = self.settings.get()
        sleep = settings["display"]["sleep"]
        local_now = self._clock().astimezone(ZoneInfo(settings["timeZone"]))
        return {"on": not is_sleeping(sleep, local_now), "powerOff": sleep["powerOff"], "cec": sleep["cec"]}

    def state(self, include_setup=False):
        settings, revision = self.settings.get()
        entries = self.store.snapshot()

        def source(key, kind):
            entry = entries.get(key) or {}
            return {"data": entry.get("data"), "fetchedAt": entry.get("fetchedAt"), "error": entry.get("error"),
                    "refreshMinutes": self.config[kind]["refreshMinutes"]}

        widgets = {}
        for widget in settings["widgets"]:
            found = self.source_of(widget)
            if found:
                widgets[widget["id"]] = source(found[0], found[1])
        state = {
            "serverTime": self._clock().isoformat(),
            "revision": self.revision(),
            "settings": settings,
            "weather": source(self.weather_key(settings), "weather"),
            "widgets": widgets,
            "setup": None,
        }
        code = self.auth.setup_code if include_setup else None
        if code and self.admin_port:
            state["setup"] = {"code": code, "urls": [f"http://{address}:{self.admin_port}" for address in lan_addresses()]}
        return state

    def upload_usage(self):
        """Upload id -> names of the places that use it."""
        settings, _ = self.settings.get()
        catalog = self.settings.catalog
        usage = {}
        if settings["logo"]:
            usage.setdefault(settings["logo"], []).append("Firmenlogo")
        for widget in settings["widgets"]:
            label = catalog["types"][widget["type"]]["label"]
            options = widget["options"]
            for value in [options.get("image")] + list(options.get("images") or []):
                if value:
                    usage.setdefault(value, []).append(f"Kachel „{label}“")
        return usage

    def uploads_with_usage(self):
        usage = self.upload_usage()
        return [{**item, "usedBy": usage.get(item["id"], [])} for item in self.uploads.list()]

    def status(self):
        settings, _ = self.settings.get()
        entries = self.store.snapshot()
        sources = [{"label": f"Wetter für {settings['location']['name']}", **self._entry(entries, self.weather_key(settings))}]
        seen = set()
        for widget in settings["widgets"]:
            found = self.source_of(widget)
            if not found or found[0] in seen:
                continue
            seen.add(found[0])
            options = widget["options"]
            label = {
                "news": lambda: f"Nachrichten „{options['title']}“",
                "stock": lambda: f"Aktie {options['symbol']}",
                "transit": lambda: f"Abfahrten {options['stop']['name']}",
            }[widget["type"]]()
            sources.append({"label": label, **self._entry(entries, found[0])})
        with self._lock:
            screen = dict(self._screen) if self._screen else None
        updates = settings["updates"]
        return {
            "version": self.version,
            "startedAt": self._started.isoformat(),
            "serverTime": self._clock().isoformat(),
            "addresses": [f"http://{address}:{self.admin_port}" for address in lan_addresses()] if self.admin_port else [],
            "screen": screen,
            "sources": sources,
            "updates": {**updates, **(self.updater.status if self.updater else {})},
        }

    def tick(self):
        """Scheduler work besides the sources: the nightly update."""
        if not self.updater:
            return
        settings, _ = self.settings.get()
        if self.updater.due(settings, self._clock().astimezone(ZoneInfo(settings["timeZone"]))):
            self.updater.start()

    @staticmethod
    def _entry(entries, key):
        entry = entries.get(key) or {}
        return {"fetchedAt": entry.get("fetchedAt"), "error": entry.get("error")}


def make_server(kiosk, host, port, handler):
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    server.kiosk = kiosk
    return server


def _scheduler(kiosk, stop):
    while not stop.is_set():
        kiosk.run_due()
        kiosk.tick()
        stop.wait(SCHEDULER_TICK_SECONDS)


def self_test():
    """Loads everything a start needs; the updater runs this before it keeps a new version."""
    config = load_config(None)
    catalog = load_catalog()
    default_settings(config, catalog)
    log.info("Self-test passed")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serves the office kiosk screen and its admin interface.")
    home = Path.home()
    config_dir = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "kiosk"
    cache_dir = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / "kiosk"
    data_dir = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "kiosk"
    parser.add_argument("--config", default=str(config_dir / "config.json"), help="owner configuration (JSON); optional")
    parser.add_argument("--state-dir", default=str(config_dir), help="where settings and the admin password are kept")
    parser.add_argument("--data-dir", default=str(data_dir), help="where uploaded images are kept")
    parser.add_argument("--cache-dir", default=str(cache_dir), help="where the last good data is kept")
    parser.add_argument("--port", type=int, help="overrides the screen port from the configuration")
    parser.add_argument("--admin-port", type=int, help="overrides the admin port from the configuration")
    parser.add_argument("--verbose", action="store_true", help="log every request")
    parser.add_argument("--self-test", action="store_true", help="check that this version can start, then exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    if args.self_test:
        try:
            return self_test()
        except Exception:  # noqa: BLE001 - any failure means: do not keep this version
            log.exception("Self-test failed")
            return 1
    try:
        config = load_config(args.config)
    except (ConfigError, OSError) as err:
        log.error("Cannot start: %s", err)
        return 2

    state_dir = Path(args.state_dir)
    catalog = load_catalog()
    settings = SettingsStore(state_dir / "settings.json", catalog, default_settings(config, catalog))
    kiosk = Kiosk(config, Store(args.cache_dir), settings, Auth(state_dir / "admin.json"), Uploads(Path(args.data_dir) / "uploads"))

    servers = []
    port = args.port if args.port is not None else int(config["port"])
    admin_port = args.admin_port if args.admin_port is not None else config.get("adminPort")
    try:
        servers.append(make_server(kiosk, config["host"], port, ScreenHandler))
        if admin_port:
            servers.append(make_server(kiosk, config["adminHost"], int(admin_port), AdminHandler))
            kiosk.admin_port = servers[-1].server_address[1]
    except OSError as err:
        log.error("Cannot listen: %s", err)
        return 2

    restart = threading.Event()

    def after_update():
        restart.set()
        # shutdown() waits for serve_forever, so it runs in its own thread.
        threading.Thread(target=servers[0].shutdown, daemon=True).start()

    kiosk.updater = Updater(kiosk._clock, after_update, state_dir / "update-status.json")
    stop = threading.Event()
    threading.Thread(target=_scheduler, args=(kiosk, stop), name="scheduler", daemon=True).start()
    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, name="admin", daemon=True).start()
    log.info("Serving the screen on http://%s:%s", config["host"], servers[0].server_address[1])
    if kiosk.admin_port:
        log.info("Admin interface on port %s: %s", kiosk.admin_port, ", ".join(kiosk.status()["addresses"]) or "no network")
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for server in servers[1:]:
            server.shutdown()
        for server in servers:
            server.server_close()
    if restart.is_set():
        log.info("Restarting with the new version")
        return RESTART_EXIT_CODE
    return 0
