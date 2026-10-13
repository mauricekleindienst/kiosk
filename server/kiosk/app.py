"""The kiosk server: refreshes weather and news in the background and serves the screen."""

import argparse
import functools
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from . import feeds, http_client, weather
from .config import ConfigError, load_config
from .store import Store

log = logging.getLogger("kiosk")

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
# After a failed refresh, try again sooner than the regular interval, but do not hammer the source.
RETRY_SECONDS = 60
SCHEDULER_TICK_SECONDS = 5

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-cache",
}


def _utc_now():
    return datetime.now(timezone.utc)


class Kiosk:
    """Owns the configuration, the data sources and their refresh schedule."""

    def __init__(self, config, store, fetch=http_client.fetch, fetch_json=http_client.fetch_json, clock=_utc_now):
        self.config = config
        self.store = store
        self._fetch = fetch
        self._fetch_json = fetch_json
        self._clock = clock
        self._tz = ZoneInfo(config["timeZone"])
        self.sources = {
            "weather": (self._refresh_weather, config["weather"]["refreshMinutes"] * 60),
            "news-main": (functools.partial(self._refresh_news, "main"), config["news"]["refreshMinutes"] * 60),
            "news-side": (functools.partial(self._refresh_news, "side"), config["news"]["refreshMinutes"] * 60),
        }
        self._due = {name: 0.0 for name in self.sources}

    def _refresh_weather(self, now):
        location = self.config["location"]
        urls = weather.request_urls(
            self.config["weather"]["baseUrl"], location["lat"], location["lon"],
            self.config["timeZone"], now.astimezone(self._tz).date(),
        )
        current = self._fetch_json(urls["current"])
        forecast = self._fetch_json(urls["forecast"])
        try:
            alerts = self._fetch_json(urls["alerts"])
        except http_client.FetchError as err:
            # Warnings are an extra; a failing alerts endpoint must not hide the forecast.
            log.warning("Weather warnings unavailable, showing the forecast without them: %s", err)
            alerts = None
        return weather.build_weather(
            current, forecast, alerts, now, location["name"], location["lat"], location["lon"], self._tz,
        )

    def _refresh_news(self, key, now):
        feed = self.config["news"][key]
        headlines = feeds.parse_feed(self._fetch(feed["url"], accept="application/rss+xml, application/atom+xml, text/xml"))
        picked = feeds.select_headlines(headlines, now, int(feed["limit"]), float(self.config["news"]["maxAgeDays"]))
        return [headline.to_json() for headline in picked]

    def run_due(self, monotonic_now):
        """Refreshes every source whose time has come. Called by the scheduler thread and by tests."""
        for name, (refresh, interval) in self.sources.items():
            if monotonic_now < self._due[name]:
                continue
            now = self._clock()
            try:
                data = refresh(now)
            except (http_client.FetchError, feeds.FeedError) as err:
                log.warning("Refreshing %s failed, keeping the last good data: %s", name, err)
                self.store.fail(name, str(err))
                self._due[name] = monotonic_now + min(RETRY_SECONDS, interval)
                continue
            except Exception as err:  # noqa: BLE001 - an unexpected answer must not stop the scheduler
                log.exception("Refreshing %s failed on an unexpected answer, keeping the last good data", name)
                self.store.fail(name, str(err))
                self._due[name] = monotonic_now + min(RETRY_SECONDS, interval)
                continue
            self.store.put(name, data, now.isoformat())
            self._due[name] = monotonic_now + interval
            log.info("Refreshed %s", name)

    def state(self):
        """The JSON the screen polls: data, when it was fetched, and the last error per source."""
        entries = self.store.snapshot()

        def source(name, extra):
            entry = entries.get(name) or {}
            return {"data": entry.get("data"), "fetchedAt": entry.get("fetchedAt"), "error": entry.get("error"), **extra}

        news = self.config["news"]
        return {
            "serverTime": self._clock().isoformat(),
            "timeZone": self.config["timeZone"],
            "display": {"reloadAt": self.config["display"]["reloadAt"]},
            "weather": source("weather", {"refreshMinutes": self.config["weather"]["refreshMinutes"]}),
            "news": {
                key: source(f"news-{key}", {"title": news[key]["title"], "refreshMinutes": news["refreshMinutes"]})
                for key in ("main", "side")
            },
        }


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".css": "text/css",
        ".svg": "image/svg+xml",
        ".woff2": "font/woff2",
        ".json": "application/json",
    }

    def __init__(self, *args, kiosk, **kwargs):
        self.kiosk = kiosk
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def end_headers(self):
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            self._send_json(self.kiosk.state())
        elif path == "/api/health":
            self._send_json({"ok": True})
        elif path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND)
        else:
            super().do_GET()

    def list_directory(self, path):
        self.send_error(HTTPStatus.NOT_FOUND)
        return None

    def _send_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        log.debug("%s %s", self.address_string(), format % args)


def make_server(kiosk, host, port):
    return ThreadingHTTPServer((host, port), functools.partial(Handler, kiosk=kiosk))


def _scheduler(kiosk, stop):
    while not stop.is_set():
        kiosk.run_due(time.monotonic())
        stop.wait(SCHEDULER_TICK_SECONDS)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serves the office kiosk screen.")
    default_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kiosk" / "config.json"
    default_cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "kiosk"
    parser.add_argument("--config", default=str(default_config), help="owner configuration (JSON); optional")
    parser.add_argument("--cache-dir", default=str(default_cache), help="where the last good data is kept")
    parser.add_argument("--port", type=int, help="overrides the port from the configuration")
    parser.add_argument("--verbose", action="store_true", help="log every request")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = load_config(args.config)
    except (ConfigError, OSError) as err:
        log.error("Cannot start: %s", err)
        return 2

    store = Store(args.cache_dir)
    kiosk = Kiosk(config, store)
    store.load(kiosk.sources)
    port = args.port if args.port is not None else int(config["port"])
    try:
        server = make_server(kiosk, config["host"], port)
    except OSError as err:
        log.error("Cannot listen on %s:%s: %s", config["host"], port, err)
        return 2

    stop = threading.Event()
    threading.Thread(target=_scheduler, args=(kiosk, stop), name="scheduler", daemon=True).start()
    log.info("Serving the kiosk on http://%s:%s", config["host"], server.server_address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
    return 0
