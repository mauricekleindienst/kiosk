"""Admin access: one password (scrypt), server-side sessions, a lockout after failed attempts, and
the one-time setup code the screen shows until a password exists."""

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from pathlib import Path

from .fsutil import atomic_write_json

log = logging.getLogger("kiosk")

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 200
# scrypt cost: about 50 ms on a Raspberry Pi 4, too slow for guessing at scale.
SCRYPT = {"n": 2**14, "r": 8, "p": 1}
SESSION_IDLE_SECONDS = 12 * 3600
SESSION_MAX_SECONDS = 7 * 24 * 3600
# After this many wrong passwords from one address, it waits; the wait doubles each time.
FREE_ATTEMPTS = 5
LOCKOUT_SECONDS = 30
MAX_LOCKOUT_SECONDS = 15 * 60
SETUP_CODE_ATTEMPTS = 5


class AuthError(Exception):
    def __init__(self, message, status=401, retry_after=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.retry_after = retry_after


def _hash(password, salt, params):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=params["n"], r=params["r"], p=params["p"], dklen=32)


def check_new_password(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Das Passwort braucht mindestens {MIN_PASSWORD_LENGTH} Zeichen.", status=400)
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AuthError(f"Das Passwort darf höchstens {MAX_PASSWORD_LENGTH} Zeichen haben.", status=400)


class Auth:
    def __init__(self, path, clock=time.monotonic):
        self._path = Path(path)
        self._clock = clock
        self._lock = threading.Lock()
        self._sessions = {}  # sha256(token) -> (created, last_used)
        self._failures = {}  # address -> (count, locked_until)
        self._setup_code = None
        self._setup_attempts = 0
        self._record = self._read()
        if self._record is None:
            self._new_setup_code()

    def _read(self):
        try:
            with open(self._path, encoding="utf-8") as handle:
                record = json.load(handle)
            bytes.fromhex(record["salt"]), bytes.fromhex(record["hash"])
            return record
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as err:
            log.error("Admin password file %s is unreadable; delete it to set up a new password: %s", self._path, err)
            # Fail closed: an unreadable file must not reopen the setup to anybody on the network.
            return {"salt": "", "hash": "", "broken": True}

    def _new_setup_code(self):
        self._setup_code = f"{secrets.randbelow(10**6):06d}"
        self._setup_attempts = 0
        log.info("Admin setup is open; the code is shown on the screen")

    @property
    def setup_required(self):
        with self._lock:
            return self._record is None

    @property
    def setup_code(self):
        """Only for the screen on the local port; never sent over the network."""
        with self._lock:
            return self._setup_code if self._record is None else None

    def _check_lockout(self, address):
        count, locked_until = self._failures.get(address, (0, 0.0))
        remaining = locked_until - self._clock()
        if remaining > 0:
            raise AuthError(f"Zu viele Versuche. Bitte in {int(remaining) + 1} Sekunden erneut versuchen.", 429, int(remaining) + 1)

    def _record_failure(self, address):
        count, _ = self._failures.get(address, (0, 0.0))
        count += 1
        locked_until = 0.0
        if count >= FREE_ATTEMPTS:
            locked_until = self._clock() + min(LOCKOUT_SECONDS * 2 ** (count - FREE_ATTEMPTS), MAX_LOCKOUT_SECONDS)
        self._failures[address] = (count, locked_until)

    def _store_password(self, password):
        salt = secrets.token_bytes(16)
        record = {"salt": salt.hex(), "hash": _hash(password, salt, SCRYPT).hex(), **SCRYPT}
        atomic_write_json(self._path, record, mode=0o600)
        self._record = record

    def setup(self, code, password, address):
        check_new_password(password)
        with self._lock:
            if self._record is not None:
                raise AuthError("Die Einrichtung ist bereits abgeschlossen. Bitte anmelden.", 409)
            self._check_lockout(address)
            if not isinstance(code, str) or not hmac.compare_digest(code.strip(), self._setup_code):
                self._record_failure(address)
                self._setup_attempts += 1
                if self._setup_attempts >= SETUP_CODE_ATTEMPTS:
                    self._new_setup_code()
                    raise AuthError("Der Code stimmt nicht. Der Bildschirm zeigt jetzt einen neuen Code.")
                raise AuthError("Der Code stimmt nicht. Er steht unten auf dem Kiosk-Bildschirm.")
            self._store_password(password)
            self._setup_code = None
            self._failures.pop(address, None)
            return self._new_session()

    def _verify(self, password):
        record = self._record
        if record is None or record.get("broken") or not isinstance(password, str) or len(password) > MAX_PASSWORD_LENGTH:
            return False
        params = {key: record.get(key, SCRYPT[key]) for key in SCRYPT}
        expected = bytes.fromhex(record["hash"])
        return hmac.compare_digest(_hash(password, bytes.fromhex(record["salt"]), params), expected)

    def login(self, password, address):
        with self._lock:
            if self._record is None:
                raise AuthError("Es ist noch kein Passwort eingerichtet.", 409)
            self._check_lockout(address)
            if not self._verify(password):
                self._record_failure(address)
                raise AuthError("Das Passwort stimmt nicht.")
            self._failures.pop(address, None)
            return self._new_session()

    def change_password(self, current, new, address):
        check_new_password(new)
        with self._lock:
            self._check_lockout(address)
            if not self._verify(current):
                self._record_failure(address)
                raise AuthError("Das bisherige Passwort stimmt nicht.", 400)
            self._store_password(new)
            # Everybody else signs in again with the new password.
            self._sessions.clear()
            return self._new_session()

    def _new_session(self):
        token = secrets.token_urlsafe(32)
        now = self._clock()
        # Forget expired sessions, so the table does not grow over months of logins.
        self._sessions = {
            key: (created, used) for key, (created, used) in self._sessions.items()
            if now - used <= SESSION_IDLE_SECONDS and now - created <= SESSION_MAX_SECONDS
        }
        self._sessions[hashlib.sha256(token.encode()).hexdigest()] = (now, now)
        return token

    def session_valid(self, token):
        if not token:
            return False
        key = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            session = self._sessions.get(key)
            if session is None:
                return False
            created, last_used = session
            now = self._clock()
            if now - last_used > SESSION_IDLE_SECONDS or now - created > SESSION_MAX_SECONDS:
                del self._sessions[key]
                return False
            self._sessions[key] = (created, now)
            return True

    def logout(self, token):
        if token:
            with self._lock:
                self._sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
