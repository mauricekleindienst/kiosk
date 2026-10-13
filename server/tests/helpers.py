import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from kiosk import http_client
from kiosk.app import Kiosk
from kiosk.auth import Auth
from kiosk.config import load_config
from kiosk.settings import SettingsStore, default_settings, load_catalog
from kiosk.store import Store
from kiosk.uploads import Uploads

FIXTURES = Path(__file__).parent / "fixtures"
BERLIN = ZoneInfo("Europe/Berlin")
CATALOG = load_catalog()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def fixture_bytes(name):
    return (FIXTURES / name).read_bytes()


def fixture_json(name):
    return json.loads(fixture_bytes(name))


def forecast(start, hours, icon_at=lambda moment: "partly-cloudy-day", temperature_at=None):
    """A Bright Sky /weather response with one record per hour from `start` (Berlin time)."""
    temperature_at = temperature_at or (lambda moment: 5.0 + moment.hour * 0.5)
    records = []
    for offset in range(hours):
        # Step in UTC like the real API, so a DST change yields a 23- or 25-hour day.
        moment = (start.astimezone(timezone.utc) + timedelta(hours=offset)).astimezone(start.tzinfo)
        records.append({
            "timestamp": moment.isoformat(),
            "source_id": 46164,
            "precipitation": 0.2 if icon_at(moment) == "rain" else 0.0,
            "pressure_msl": 1018.0,
            "sunshine": 30.0,
            "temperature": temperature_at(moment),
            "wind_direction": 240,
            "wind_speed": 11.0,
            "cloud_cover": 50,
            "dew_point": 4.0,
            "relative_humidity": 80,
            "visibility": 30000,
            "wind_gust_direction": None,
            "wind_gust_speed": 25.0,
            "condition": "rain" if icon_at(moment) == "rain" else "dry",
            "precipitation_probability": 60 if icon_at(moment) == "rain" else 10,
            "precipitation_probability_6h": None,
            "solar": 0.2,
            "icon": icon_at(moment),
        })
    return {"weather": records, "sources": []}


def berlin(*args):
    return datetime(*args, tzinfo=BERLIN)


class FakeUpstream:
    """Answers the kiosk's requests like Bright Sky and Google News would, or fails on demand."""

    def __init__(self):
        self.failing = set()
        self.requests = []

    def _check(self, url):
        self.requests.append(url)
        for part in self.failing:
            if part in url:
                raise http_client.FetchError(f"{url} is not reachable: fake outage")

    def fetch(self, url, accept="*/*"):
        self._check(url)
        return fixture_bytes("google-news-rheinmetall.xml")

    def fetch_json(self, url):
        self._check(url)
        if "/current_weather" in url:
            return fixture_json("brightsky-current.json")
        if "/alerts" in url:
            return fixture_json("brightsky-alerts.json")
        return forecast(berlin(2026, 10, 13, 0), 24 * 8)


class Clock:
    def __init__(self, now):
        self.now = now
        self.seconds = 1000.0

    def __call__(self):
        return self.now

    def monotonic(self):
        return self.seconds


def make_kiosk(test, upstream=None, config=None, clock=None):
    """A Kiosk with every file in a temporary folder that the test cleans up."""
    folder = tempfile.TemporaryDirectory()
    test.addCleanup(folder.cleanup)
    root = Path(folder.name)
    config = config or load_config(None)
    upstream = upstream or FakeUpstream()
    clock = clock or Clock(berlin(2026, 10, 13, 9, 41))
    settings = SettingsStore(root / "settings.json", CATALOG, default_settings(config, CATALOG))
    kiosk = Kiosk(config, Store(root / "cache"), settings, Auth(root / "admin.json", clock=clock.monotonic),
                  Uploads(root / "uploads"), upstream.fetch, upstream.fetch_json, clock, clock.monotonic)
    kiosk.root = root
    kiosk.upstream = upstream
    kiosk.clock = clock
    return kiosk
