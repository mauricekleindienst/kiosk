"""Nightly self-update: runs scripts/update.sh at the configured time (or when an admin asks) and
restarts the server after an update, so the new code runs and the screen reloads."""

import json
import logging
import os
import subprocess
import threading
from pathlib import Path

from .fsutil import atomic_write_json

log = logging.getLogger("kiosk")

ROOT = Path(__file__).resolve().parents[2]
# Tests point this at a stand-in, so they never fetch and merge in a developer's checkout.
SCRIPT = Path(os.environ.get("KIOSK_UPDATE_SCRIPT", ROOT / "scripts" / "update.sh"))
# A fetch over a slow line plus the self-test; anything longer is stuck.
TIMEOUT_SECONDS = 300
MESSAGES = {
    0: "Aktualisiert. Der Kiosk startet neu.",
    10: "Bereits aktuell.",
    20: "Kein Git-Checkout mit Upstream-Branch; automatische Updates sind hier nicht möglich.",
    30: "Lokale Änderungen im Checkout; das Update wurde nicht eingespielt.",
    40: "GitHub war nicht erreichbar oder der Zugang fehlt (Deploy Key). Siehe README, „Automatische Updates“.",
    50: "Die neue Version hat den Selbsttest nicht bestanden; die bisherige läuft weiter.",
}


def _git(*args):
    try:
        result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def installed_version(package_version):
    """"2.1.0 (a1b2c3d, 2026-10-13)" in a checkout, else the package version."""
    commit = _git("rev-parse", "--short", "HEAD")
    date = _git("log", "-1", "--format=%cs")
    return f"{package_version} ({commit}, {date})" if commit else package_version


class Updater:
    def __init__(self, clock, on_updated, status_path=None, run=subprocess.run, script=SCRIPT):
        self._clock = clock
        self._on_updated = on_updated
        self._status_path = Path(status_path) if status_path else None
        self._run = run
        self._script = script
        self._lock = threading.Lock()
        self._running = False
        self._last_day = None
        self.status = {"lastCheck": None, "result": None, "message": None, "running": False}
        # The result survives the restart that follows an update, so the admin sees what happened.
        if self._status_path and self._status_path.exists():
            try:
                stored = json.loads(self._status_path.read_text(encoding="utf-8"))
                self.status = {**self.status, **{key: stored.get(key) for key in ("lastCheck", "result", "message")}}
            except (OSError, ValueError, AttributeError) as err:
                log.warning("Ignoring unreadable update status %s: %s", self._status_path, err)

    def due(self, settings, local_now):
        """True once a day at the configured time, when updates are on."""
        updates = settings["updates"]
        if not updates["enabled"] or local_now.strftime("%H:%M") != updates["time"]:
            return False
        if self._last_day == local_now.date():
            return False
        self._last_day = local_now.date()
        return True

    def start(self):
        """Runs the update in the background; False if one is already running."""
        with self._lock:
            if self._running:
                return False
            self._running = True
            self.status = {**self.status, "running": True}
        threading.Thread(target=self._run_update, name="update", daemon=True).start()
        return True

    def _run_update(self):
        try:
            completed = self._run(["bash", str(self._script)], capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False)
            code, output = completed.returncode, (completed.stdout or "").strip()
        except subprocess.TimeoutExpired:
            code, output = 40, "timed out"
        except OSError as err:
            code, output = 20, str(err)
        message = MESSAGES.get(code, f"Unerwartetes Ergebnis ({code}).")
        log.log(logging.INFO if code in (0, 10) else logging.WARNING, "Update check: %s (%s)", output, code)
        with self._lock:
            self._running = False
            self.status = {"lastCheck": self._clock().isoformat(), "result": "updated" if code == 0 else "current" if code == 10 else "failed",
                           "message": message, "running": False}
            status = dict(self.status)
        if self._status_path:
            try:
                atomic_write_json(self._status_path, status)
            except OSError as err:
                log.warning("Could not write the update status to %s: %s", self._status_path, err)
        if code == 0:
            self._on_updated()
