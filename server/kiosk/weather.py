"""Turns Bright Sky (Deutscher Wetterdienst open data) responses into the screen's weather model."""

import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

ICONS = {
    "clear-day", "clear-night", "partly-cloudy-day", "partly-cloudy-night", "cloudy", "fog",
    "wind", "rain", "sleet", "snow", "hail", "thunderstorm",
}
_DAY_VARIANT = {"clear-night": "clear-day", "partly-cloudy-night": "partly-cloudy-day"}
# A day is summarised by its precipitation when it rains or snows for at least this many hours
# between 8 and 20 o'clock; one wet hour does not make a rainy day.
WET_HOURS_FOR_DAILY_ICON = 3
# Severe weather is worth showing even when it lasts one hour.
SEVERE_ICONS = ("thunderstorm", "hail")
WET_ICONS = ("snow", "sleet", "rain")
DAYTIME_HOURS = range(8, 21)
# Today keeps every hour since midnight (observations); a later day with fewer hours is a
# forecast that ends mid-day and would show a misleading minimum and maximum.
MIN_HOURS_PER_DAY = 18
HOURLY_COUNT = 12
DAILY_COUNT = 7
SEVERITY_RANK = {"minor": 1, "moderate": 2, "severe": 3, "extreme": 4}
MAX_ALERTS = 2


def request_urls(base_url, lat, lon, time_zone, today):
    query = {"lat": lat, "lon": lon, "tz": time_zone}
    last = today + timedelta(days=DAILY_COUNT + 1)
    return {
        "current": f"{base_url}/current_weather?{urlencode(query)}",
        "forecast": f"{base_url}/weather?{urlencode({**query, 'date': today.isoformat(), 'last_date': last.isoformat()})}",
        "alerts": f"{base_url}/alerts?{urlencode(query)}",
    }


def icon_key(raw):
    return raw if raw in ICONS else "cloudy"


def _number(value):
    return None if value is None else float(value)


def _parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def daily_icon(hourly_icons):
    """Picks the icon that best describes a day from its hourly icons (daytime hours only)."""
    if not hourly_icons:
        return "cloudy"
    counts = Counter(_DAY_VARIANT.get(icon, icon) for icon in hourly_icons)
    for icon in SEVERE_ICONS:
        if counts[icon]:
            return icon
    for icon in WET_ICONS:
        if counts[icon] >= WET_HOURS_FOR_DAILY_ICON:
            return icon
    for icon in WET_ICONS:
        counts.pop(icon, None)
    if not counts:
        return "rain"
    # Most frequent; ties go to the cloudier icon so the screen does not promise too much sun.
    order = ["cloudy", "fog", "wind", "partly-cloudy-day", "clear-day"]
    return max(counts, key=lambda icon: (counts[icon], -order.index(icon) if icon in order else -99))


def sun_times(day, lat, lon):
    """Sunrise and sunset in UTC for a calendar day, from the standard sunrise equation (accurate
    to about a minute at mid latitudes). Returns (None, None) during polar day or night."""
    n = (day - date(2000, 1, 1)).days
    mean_noon = n - lon / 360.0
    anomaly = math.radians((357.5291 + 0.98560028 * mean_noon) % 360)
    center = 1.9148 * math.sin(anomaly) + 0.0200 * math.sin(2 * anomaly) + 0.0003 * math.sin(3 * anomaly)
    longitude = math.radians((math.degrees(anomaly) + center + 180 + 102.9372) % 360)
    transit = 2451545.0 + mean_noon + 0.0053 * math.sin(anomaly) - 0.0069 * math.sin(2 * longitude)
    declination = math.asin(math.sin(longitude) * math.sin(math.radians(23.4397)))
    latitude = math.radians(lat)
    # -0.833 degrees: refraction plus the radius of the sun's disc.
    cos_hour_angle = (math.sin(math.radians(-0.833)) - math.sin(latitude) * math.sin(declination)) / (
        math.cos(latitude) * math.cos(declination)
    )
    if not -1 <= cos_hour_angle <= 1:
        return None, None
    half_day = math.degrees(math.acos(cos_hour_angle)) / 360.0

    def to_datetime(julian):
        return datetime.fromtimestamp((julian - 2440587.5) * 86400, tz=timezone.utc).replace(microsecond=0)

    return to_datetime(transit - half_day), to_datetime(transit + half_day)


def _current(raw):
    weather = (raw or {}).get("weather")
    if not weather:
        return None
    precipitation = weather.get("precipitation_60")
    if precipitation is None:
        precipitation = weather.get("precipitation_10")
    return {
        "temperature": _number(weather.get("temperature")),
        "icon": icon_key(weather.get("icon")),
        "windSpeed": _number(weather.get("wind_speed_10")),
        "windGust": _number(weather.get("wind_gust_speed_10")),
        "humidity": _number(weather.get("relative_humidity")),
        "precipitation": _number(precipitation),
        "observedAt": weather.get("timestamp"),
    }


def _alerts(raw, now):
    alerts = []
    for alert in (raw or {}).get("alerts") or []:
        expires = alert.get("expires")
        if expires and _parse_time(expires) < now:
            continue
        severity = alert.get("severity") or "minor"
        alerts.append({
            "severity": severity,
            "event": alert.get("event_de") or alert.get("event_en") or "",
            "headline": alert.get("headline_de") or alert.get("headline_en") or "",
            "onset": alert.get("onset"),
            "expires": expires,
        })
    alerts.sort(key=lambda alert: -SEVERITY_RANK.get(alert["severity"], 0))
    return alerts[:MAX_ALERTS]


def build_weather(current_raw, forecast_raw, alerts_raw, now, location_name, lat, lon, tz):
    """Combines the three Bright Sky responses. `now` is timezone-aware; `tz` is a ZoneInfo."""
    records = []
    for record in (forecast_raw or {}).get("weather") or []:
        if record.get("timestamp") is None:
            continue
        records.append((_parse_time(record["timestamp"]).astimezone(tz), record))
    records.sort(key=lambda pair: pair[0])
    if not records:
        raise ValueError("forecast has no hourly records")

    hour_start = now.astimezone(tz).replace(minute=0, second=0, microsecond=0)
    hourly = [
        {
            "time": moment.isoformat(),
            "temperature": _number(record.get("temperature")),
            "icon": icon_key(record.get("icon")),
            "precipitationProbability": _number(record.get("precipitation_probability")),
        }
        for moment, record in records
        if moment >= hour_start
    ][:HOURLY_COUNT]

    by_day = defaultdict(list)
    for moment, record in records:
        by_day[moment.date()].append((moment, record))
    today = now.astimezone(tz).date()
    daily = []
    for day in sorted(by_day):
        if day < today:
            continue
        hours = by_day[day]
        if day != today and len(hours) < MIN_HOURS_PER_DAY:
            continue
        temperatures = [r["temperature"] for _, r in hours if r.get("temperature") is not None]
        if not temperatures:
            continue
        probabilities = [r["precipitation_probability"] for _, r in hours if r.get("precipitation_probability") is not None]
        daily.append({
            "date": day.isoformat(),
            "min": min(temperatures),
            "max": max(temperatures),
            "icon": daily_icon([r.get("icon") for m, r in hours if m.hour in DAYTIME_HOURS and r.get("icon")]),
            "precipitationProbability": max(probabilities) if probabilities else None,
            "precipitation": round(sum(r.get("precipitation") or 0 for _, r in hours), 1),
        })
        if len(daily) == DAILY_COUNT:
            break

    sunrise, sunset = sun_times(today, lat, lon)
    return {
        "location": location_name,
        "current": _current(current_raw),
        "hourly": hourly,
        "daily": daily,
        "sun": {
            "sunrise": sunrise.astimezone(tz).isoformat() if sunrise else None,
            "sunset": sunset.astimezone(tz).isoformat() if sunset else None,
        },
        "alerts": _alerts(alerts_raw, now),
    }
