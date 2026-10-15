"""Uploaded images (logo, slideshow). The type comes from the file's content, never from the
client; files are stored under a content hash, so a name can never escape the folder."""

import hashlib
import json
import logging
import re
import threading
import time
from pathlib import Path

from .fsutil import atomic_write_bytes, atomic_write_json

log = logging.getLogger("kiosk")

MAX_BYTES = 20 * 1024 * 1024  # animated GIFs are often larger than photos
MAX_FILES = 200
_ID = re.compile(r"^[0-9a-f]{20}\.(png|jpg|webp|gif|svg)$")
CONTENT_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "gif": "image/gif", "svg": "image/svg+xml"}
_NAME_CLEAN = re.compile(r"[\x00-\x1f\x7f/\\]")


class UploadError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def detect_type(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    head = data[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if (head.startswith(b"<svg") or head.startswith(b"<?xml")) and b"<svg" in head:
        return "svg"
    return None


def is_upload_id(value):
    return isinstance(value, str) and bool(_ID.match(value))


class Uploads:
    def __init__(self, directory, clock=time.time):
        self._dir = Path(directory)
        self._index_path = self._dir / "uploads.json"
        self._clock = clock
        self._lock = threading.Lock()
        self._items = self._read_index()

    def _read_index(self):
        try:
            with open(self._index_path, encoding="utf-8") as handle:
                items = json.load(handle)
            return [item for item in items if is_upload_id(item.get("id")) and (self._dir / item["id"]).exists()]
        except FileNotFoundError:
            return []
        except (OSError, ValueError, AttributeError) as err:
            log.warning("Upload index %s is unreadable, starting empty: %s", self._index_path, err)
            return []

    def ids(self):
        with self._lock:
            return {item["id"] for item in self._items}

    def list(self):
        with self._lock:
            return [dict(item) for item in self._items]

    def path(self, upload_id):
        """The file of an upload, or None. Only ids that match the strict pattern reach the disk."""
        if not is_upload_id(upload_id):
            return None
        path = self._dir / upload_id
        return path if path.exists() else None

    def add(self, data, name):
        if not data:
            raise UploadError("Die Datei ist leer.")
        if len(data) > MAX_BYTES:
            raise UploadError(f"Die Datei ist größer als {MAX_BYTES // (1024 * 1024)} MB.", 413)
        kind = detect_type(data)
        if kind is None:
            raise UploadError("Nur Bilder im Format PNG, JPEG, WebP, GIF oder SVG.", 415)
        upload_id = f"{hashlib.sha256(data).hexdigest()[:20]}.{kind}"
        display_name = _NAME_CLEAN.sub("", name or "")[:120].strip() or upload_id
        with self._lock:
            existing = next((item for item in self._items if item["id"] == upload_id), None)
            if existing:
                return dict(existing)
            if len(self._items) >= MAX_FILES:
                raise UploadError(f"Es sind schon {MAX_FILES} Bilder hochgeladen. Bitte erst alte löschen.", 409)
            atomic_write_bytes(self._dir / upload_id, data)
            item = {"id": upload_id, "name": display_name, "type": CONTENT_TYPES[kind], "size": len(data),
                    "uploadedAt": int(self._clock())}
            self._items.append(item)
            atomic_write_json(self._index_path, self._items)
            return dict(item)

    def remove(self, upload_id):
        with self._lock:
            before = len(self._items)
            self._items = [item for item in self._items if item["id"] != upload_id]
            if len(self._items) == before:
                raise UploadError("Das Bild gibt es nicht.", 404)
            atomic_write_json(self._index_path, self._items)
            path = self._dir / upload_id
            if is_upload_id(upload_id) and path.exists():
                path.unlink()
