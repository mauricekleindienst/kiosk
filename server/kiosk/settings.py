"""The screen's settings: layout, widgets and their options, location and display. Edited in the
admin interface, validated here against the widget catalog (web/shared/widgets.json, shared with
the admin forms and the screen), stored atomically in ~/.config/kiosk/settings.json."""

import copy
import json
import logging
import re
import threading
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .fsutil import atomic_write_json

log = logging.getLogger("kiosk")

CATALOG_PATH = Path(__file__).resolve().parents[2] / "web" / "shared" / "widgets.json"
SETTINGS_VERSION = 1
_ID = re.compile(r"^[a-z0-9-]{1,32}$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
SCALE_RANGE = (80, 140)
DENSITIES = ("compact", "normal", "airy")


class SettingsError(ValueError):
    """An invalid value, with the path to it so the admin form can point at the field."""

    def __init__(self, message, path=""):
        super().__init__(message)
        self.message = message
        self.path = path


class ConflictError(Exception):
    """The settings changed since the client loaded them (another admin, another tab)."""


def load_catalog(path=CATALOG_PATH):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _require(condition, message, path):
    if not condition:
        raise SettingsError(message, path)


def _text(value, path, max_length, required=False, multiline=False):
    _require(isinstance(value, str), "Bitte einen Text eingeben.", path)
    value = value.strip() if not multiline else value.replace("\r\n", "\n").strip()
    _require(not _CONTROL.search(value) and (multiline or "\n" not in value), "Der Text enthält ungültige Zeichen.", path)
    _require(len(value) <= max_length, f"Höchstens {max_length} Zeichen.", path)
    _require(value or not required, "Dieses Feld darf nicht leer sein.", path)
    return value


def _date(value, path, required):
    if value is None or value == "":
        _require(not required, "Bitte ein Datum wählen.", path)
        return None
    _require(isinstance(value, str), "Bitte ein Datum wählen.", path)
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as err:
        raise SettingsError("Bitte ein gültiges Datum wählen.", path) from err


def _time(value, path):
    _require(isinstance(value, str) and _TIME.match(value), "Bitte eine Uhrzeit wie 07:30 eingeben.", path)
    return value


def _time_zone(value, path):
    _require(isinstance(value, str) and value, "Bitte eine Zeitzone wählen.", path)
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as err:
        raise SettingsError(f"Die Zeitzone „{value}“ ist unbekannt.", path) from err
    return value


def _option(spec, value, path, upload_ids):
    kind = spec["type"]
    required = spec.get("required", False)
    if kind in ("text", "textarea"):
        return _text(value, path, spec.get("maxLength", 200), required, multiline=kind == "textarea")
    if kind == "url":
        value = _text(value, path, 2000, required=True)
        parts = urlsplit(value)
        _require(parts.scheme in ("http", "https") and parts.netloc, "Bitte eine Adresse mit http:// oder https:// eingeben.", path)
        return value
    if kind == "number":
        _require(isinstance(value, int) and not isinstance(value, bool), "Bitte eine ganze Zahl eingeben.", path)
        _require(spec["min"] <= value <= spec["max"], f"Bitte eine Zahl von {spec['min']} bis {spec['max']} eingeben.", path)
        return value
    if kind == "boolean":
        _require(isinstance(value, bool), "Bitte ein- oder ausschalten.", path)
        return value
    if kind == "select":
        _require(value in [choice["value"] for choice in spec["choices"]], "Bitte eine der Möglichkeiten wählen.", path)
        return value
    if kind == "date":
        return _date(value, path, required)
    if kind == "time":
        return _time(value, path)
    if kind == "image":
        if value is None:
            return None
        _require(upload_ids is None or value in upload_ids, "Das gewählte Bild gibt es nicht mehr.", path)
        return value
    if kind == "images":
        _require(isinstance(value, list), "Bitte Bilder auswählen.", path)
        _require(len(value) <= spec.get("maxItems", 30), f"Höchstens {spec.get('maxItems', 30)} Bilder.", path)
        _require(len(set(value)) == len(value), "Jedes Bild nur einmal.", path)
        for index, item in enumerate(value):
            _require(upload_ids is None or item in upload_ids, "Ein gewähltes Bild gibt es nicht mehr.", f"{path}.{index}")
        return list(value)
    if kind == "zones":
        _require(isinstance(value, list), "Bitte Standorte angeben.", path)
        _require(len(value) <= spec.get("maxItems", 6), f"Höchstens {spec.get('maxItems', 6)} Standorte.", path)
        zones = []
        for index, item in enumerate(value):
            _require(isinstance(item, dict) and set(item) == {"label", "timeZone"}, "Ungültiger Standort.", f"{path}.{index}")
            zones.append({
                "label": _text(item["label"], f"{path}.{index}.label", 40, required=True),
                "timeZone": _time_zone(item["timeZone"], f"{path}.{index}.timeZone"),
            })
        return zones
    raise SettingsError(f"Unbekannter Feldtyp {kind}.", path)


def _widget(raw, index, catalog, upload_ids):
    path = f"widgets.{index}"
    _require(isinstance(raw, dict), "Ungültige Kachel.", path)
    unknown = set(raw) - {"id", "type", "x", "y", "w", "h", "options"}
    _require(not unknown, f"Unbekannte Angaben: {', '.join(sorted(unknown))}.", path)
    _require(isinstance(raw.get("id"), str) and _ID.match(raw["id"]), "Ungültige Kachel-Kennung.", f"{path}.id")
    kind = catalog["types"].get(raw.get("type"))
    _require(kind is not None, f"Unbekannte Kachelart „{raw.get('type')}“.", f"{path}.type")
    grid = catalog["grid"]
    for key in ("x", "y", "w", "h"):
        _require(isinstance(raw.get(key), int) and not isinstance(raw.get(key), bool), "Ungültige Position oder Größe.", f"{path}.{key}")
    x, y, w, h = raw["x"], raw["y"], raw["w"], raw["h"]
    minimum = kind["minSize"]
    _require(w >= minimum["w"] and h >= minimum["h"],
             f"„{kind['label']}“ braucht mindestens {minimum['w']} × {minimum['h']} Felder.", f"{path}.w")
    _require(x >= 0 and y >= 0 and x + w <= grid["columns"] and y + h <= grid["rows"],
             "Die Kachel ragt über den Bildschirm hinaus.", f"{path}.x")

    options = raw.get("options", {})
    _require(isinstance(options, dict), "Ungültige Einstellungen.", f"{path}.options")
    specs = {spec["key"]: spec for spec in kind["options"]}
    unknown = set(options) - set(specs)
    _require(not unknown, f"Unbekannte Einstellungen: {', '.join(sorted(unknown))}.", f"{path}.options")
    normalized = {}
    for key, spec in specs.items():
        value = options[key] if key in options else copy.deepcopy(spec.get("default"))
        normalized[key] = _option(spec, value, f"{path}.options.{key}", upload_ids)
    return {"id": raw["id"], "type": raw["type"], "x": x, "y": y, "w": w, "h": h, "options": normalized}


def validate(raw, catalog, upload_ids=None):
    """Returns a normalized copy of `raw` (defaults filled in) or raises SettingsError.
    `upload_ids` is the set of existing uploads; None skips that check (used for defaults)."""
    _require(isinstance(raw, dict), "Ungültige Einstellungen.", "")
    known = {"version", "location", "timeZone", "appearance", "display", "logo", "widgets"}
    unknown = set(raw) - known
    _require(not unknown, f"Unbekannte Angaben: {', '.join(sorted(unknown))}.", "")

    location = raw.get("location")
    _require(isinstance(location, dict), "Bitte einen Standort angeben.", "location")
    for key, low, high in (("lat", -90, 90), ("lon", -180, 180)):
        value = location.get(key)
        _require(isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high,
                 f"Bitte eine Zahl von {low} bis {high} eingeben.", f"location.{key}")

    appearance = raw.get("appearance", {})
    scale = appearance.get("scale", 100)
    _require(isinstance(scale, int) and not isinstance(scale, bool) and SCALE_RANGE[0] <= scale <= SCALE_RANGE[1],
             f"Bitte eine Größe von {SCALE_RANGE[0]} bis {SCALE_RANGE[1]} % wählen.", "appearance.scale")
    density = appearance.get("density", "normal")
    _require(density in DENSITIES, "Bitte einen Abstand wählen.", "appearance.density")

    display = raw.get("display", {})
    sleep = display.get("sleep", {})
    _require(isinstance(sleep.get("enabled", False), bool) and isinstance(sleep.get("weekends", False), bool),
             "Bitte ein- oder ausschalten.", "display.sleep")

    logo = raw.get("logo")
    _require(logo is None or upload_ids is None or logo in upload_ids, "Das Logo gibt es nicht mehr.", "logo")

    widgets = raw.get("widgets")
    _require(isinstance(widgets, list), "Ungültige Kacheln.", "widgets")
    _require(len(widgets) <= catalog["maxWidgets"], f"Höchstens {catalog['maxWidgets']} Kacheln.", "widgets")
    normalized_widgets = [_widget(item, index, catalog, upload_ids) for index, item in enumerate(widgets)]
    ids = [widget["id"] for widget in normalized_widgets]
    _require(len(set(ids)) == len(ids), "Zwei Kacheln haben dieselbe Kennung.", "widgets")
    occupied = {}
    for index, widget in enumerate(normalized_widgets):
        for cx in range(widget["x"], widget["x"] + widget["w"]):
            for cy in range(widget["y"], widget["y"] + widget["h"]):
                other = occupied.setdefault((cx, cy), index)
                _require(other == index, "Zwei Kacheln überlappen sich.", f"widgets.{index}")

    return {
        "version": SETTINGS_VERSION,
        "location": {
            "name": _text(location.get("name", ""), "location.name", 60, required=True),
            "lat": float(location["lat"]),
            "lon": float(location["lon"]),
        },
        "timeZone": _time_zone(raw.get("timeZone"), "timeZone"),
        "appearance": {"scale": scale, "density": density},
        "display": {
            "reloadAt": _time(display.get("reloadAt", "03:30"), "display.reloadAt"),
            "sleep": {
                "enabled": sleep.get("enabled", False),
                "from": _time(sleep.get("from", "19:00"), "display.sleep.from"),
                "to": _time(sleep.get("to", "07:00"), "display.sleep.to"),
                "weekends": sleep.get("weekends", False),
            },
        },
        "logo": logo,
        "widgets": normalized_widgets,
    }


def default_settings(config, catalog):
    """The first layout: the screen as it looked before the admin interface existed, built from
    the configuration file so an owner's location and feeds carry over."""
    news = config["news"]
    return validate({
        "location": config["location"],
        "timeZone": config["timeZone"],
        "display": {"reloadAt": config["display"]["reloadAt"]},
        "logo": None,
        "widgets": [
            {"id": "clock", "type": "clock", "x": 0, "y": 0, "w": 7, "h": 2, "options": {}},
            {"id": "news-main", "type": "news", "x": 0, "y": 2, "w": 7, "h": 4, "options": {
                "title": news["main"]["title"], "url": news["main"]["url"], "limit": int(news["main"]["limit"]),
            }},
            {"id": "news-side", "type": "news", "x": 0, "y": 6, "w": 7, "h": 2, "options": {
                "title": news["side"]["title"], "url": news["side"]["url"], "limit": int(news["side"]["limit"]),
                "lead": False, "columns": "2",
            }},
            {"id": "weather", "type": "weather", "x": 7, "y": 0, "w": 5, "h": 8, "options": {}},
        ],
    }, catalog)


class SettingsStore:
    """Owns the current settings and their revision. Thread-safe; listeners run after a save."""

    def __init__(self, path, catalog, defaults):
        self._path = Path(path)
        self.catalog = catalog
        self._lock = threading.Lock()
        self._settings = defaults
        self._revision = 0
        self._listeners = []
        self._load()

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as handle:
                stored = json.load(handle)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as err:
            log.error("Settings file %s is unreadable, using the default layout until an admin saves: %s", self._path, err)
            return
        try:
            revision = int(stored.pop("revision", 0))
            # Uploads are not known yet at start; references are checked on every save.
            self._settings = validate(stored, self.catalog)
            self._revision = revision
        except (SettingsError, ValueError) as err:
            log.error("Settings file %s is invalid (%s), using the default layout until an admin saves", self._path, err)

    def on_change(self, listener):
        self._listeners.append(listener)

    def get(self):
        with self._lock:
            return copy.deepcopy(self._settings), self._revision

    @property
    def revision(self):
        with self._lock:
            return self._revision

    def update(self, raw, expected_revision, upload_ids):
        normalized = validate(raw, self.catalog, upload_ids)
        with self._lock:
            if expected_revision != self._revision:
                raise ConflictError()
            revision = self._revision + 1
            atomic_write_json(self._path, {**normalized, "revision": revision})
            self._settings = normalized
            self._revision = revision
        for listener in self._listeners:
            listener(copy.deepcopy(normalized))
        return copy.deepcopy(normalized), revision
