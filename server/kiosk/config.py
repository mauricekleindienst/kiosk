"""Loads the kiosk configuration: the defaults from the repository, overlaid by the owner's file."""

import json
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.default.json"


class ConfigError(Exception):
    pass


def _merge(base, override):
    """Deep-merges two dicts; values from `override` win, nested dicts merge key by key."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as err:
        raise ConfigError(f"{path} is not valid JSON (line {err.lineno}): {err.msg}") from err
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    return data


def _validate(config):
    location = config["location"]
    if not -90 <= float(location["lat"]) <= 90 or not -180 <= float(location["lon"]) <= 180:
        raise ConfigError("location.lat must be within -90..90 and location.lon within -180..180")
    for key in ("main", "side"):
        feed = config["news"][key]
        if not str(feed.get("url", "")).startswith(("http://", "https://")):
            raise ConfigError(f"news.{key}.url must be an http(s) URL")
        if int(feed.get("limit", 0)) < 1:
            raise ConfigError(f"news.{key}.limit must be at least 1")
    for section in ("weather", "news", "stock", "transit"):
        if float(config[section]["refreshMinutes"]) < 1:
            raise ConfigError(f"{section}.refreshMinutes must be at least 1")
        if not str(config[section].get("baseUrl", "https://")).startswith(("http://", "https://")):
            raise ConfigError(f"{section}.baseUrl must be an http(s) URL")
    admin_port = config.get("adminPort")
    if admin_port is not None and not (isinstance(admin_port, int) and 0 <= admin_port <= 65535):
        raise ConfigError("adminPort must be a port number, or null to switch the admin interface off")
    hours, _, minutes = str(config["display"]["reloadAt"]).partition(":")
    if not (hours.isdigit() and minutes.isdigit() and int(hours) < 24 and int(minutes) < 60):
        raise ConfigError('display.reloadAt must look like "03:30"')


def load_config(path=None):
    """Returns the effective configuration. A missing owner file means: defaults only."""
    config = _read_json(DEFAULT_CONFIG_PATH)
    if path is not None and Path(path).exists():
        config = _merge(config, _read_json(path))
    try:
        _validate(config)
    except (KeyError, TypeError, ValueError) as err:
        raise ConfigError(f"configuration is incomplete or has a wrong type: {err}") from err
    return config
