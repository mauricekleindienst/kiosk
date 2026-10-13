"""Keeps the last good result of every data source in memory and on disk, so the screen shows
the last known weather and news after a reboot without network instead of an empty page."""

import json
import logging
import threading
from pathlib import Path

from .fsutil import atomic_write_json

log = logging.getLogger("kiosk")


class Store:
    def __init__(self, cache_dir):
        self._dir = Path(cache_dir)
        self._lock = threading.Lock()
        self._entries = {}

    def load(self, names):
        """Reads the cached data of sources that are not in memory yet."""
        for name in names:
            with self._lock:
                if name in self._entries:
                    continue
            path = self._dir / f"{name}.json"
            try:
                with open(path, encoding="utf-8") as handle:
                    entry = json.load(handle)
                if isinstance(entry, dict) and "data" in entry and "fetchedAt" in entry:
                    self._entries[name] = {"data": entry["data"], "fetchedAt": entry["fetchedAt"], "error": None}
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as err:
                log.warning("Ignoring unreadable cache file %s: %s", path, err)

    def put(self, name, data, fetched_at):
        entry = {"data": data, "fetchedAt": fetched_at, "error": None}
        with self._lock:
            self._entries[name] = entry
        self._persist(name, entry)

    def fail(self, name, message):
        """Records a failed refresh; the last good data stays and is shown with its age."""
        with self._lock:
            entry = dict(self._entries.get(name) or {"data": None, "fetchedAt": None})
            entry["error"] = message
            self._entries[name] = entry

    def snapshot(self):
        with self._lock:
            return {name: dict(entry) for name, entry in self._entries.items()}

    def _persist(self, name, entry):
        try:
            atomic_write_json(self._dir / f"{name}.json", {"data": entry["data"], "fetchedAt": entry["fetchedAt"]})
        except OSError as err:
            log.warning("Could not write cache for %s to %s: %s", name, self._dir, err)
