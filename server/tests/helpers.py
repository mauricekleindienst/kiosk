import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

FIXTURES = Path(__file__).parent / "fixtures"
BERLIN = ZoneInfo("Europe/Berlin")


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
