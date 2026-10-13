"""Departures for the transit widget from a transport.rest API (default: v6.db.transport.rest, the
open interface to Deutsche Bahn's timetable, which includes trams and buses of KVG and NVV)."""

from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

PRODUCTS = ("tram", "bus", "suburban", "subway", "regional", "regionalExpress", "national", "nationalExpress", "ferry", "taxi")
# How far ahead to ask, and how many departures to keep for the screen's own limit and walk time.
DURATION_MINUTES = 90
KEPT = 30


def departures_url(base_url, stop_id, products):
    query = {"duration": DURATION_MINUTES, "results": KEPT * 2, "remarks": "false"}
    for product in PRODUCTS:
        query[product] = "true" if product in products else "false"
    return f"{base_url}/stops/{quote(stop_id, safe='')}/departures?{urlencode(query)}"


def locations_url(base_url, text):
    query = {"query": text, "results": 8, "stops": "true", "addresses": "false", "poi": "false"}
    return f"{base_url}/locations?{urlencode(query)}"


def _parse(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None


def build_departures(raw, now):
    """Upcoming departures, soonest first. Cancelled ones stay in the list, marked."""
    items = raw.get("departures") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError("transit provider sent no departure list")
    departures = []
    for item in items:
        line = item.get("line") or {}
        planned = _parse(item.get("plannedWhen"))
        actual = _parse(item.get("when"))
        moment = actual or planned
        if moment is None or moment < now - timedelta(minutes=1):
            continue
        delay = item.get("delay")
        departures.append({
            "line": line.get("name") or "",
            "product": line.get("product") or "",
            "direction": item.get("direction") or "",
            "planned": planned.isoformat() if planned else None,
            "when": moment.isoformat(),
            "delayMinutes": None if delay is None else round(delay / 60),
            "platform": item.get("platform") or item.get("plannedPlatform"),
            "cancelled": bool(item.get("cancelled")),
        })
    departures.sort(key=lambda departure: departure["when"])
    return departures[:KEPT]


def build_stops(raw):
    """Search results for the admin: stops and stations only, with id and name."""
    stops = []
    for item in raw if isinstance(raw, list) else []:
        if item.get("type") in ("stop", "station") and item.get("id") and item.get("name"):
            stops.append({"id": str(item["id"]), "name": item["name"]})
    return stops
