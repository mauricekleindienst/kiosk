"""HTTP handlers. The screen port (127.0.0.1) serves the screen without login; the admin port
(the local network) serves the admin interface and a preview of the screen behind a login."""

import json
import logging
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .auth import SESSION_MAX_SECONDS, AuthError
from .settings import ConflictError, SettingsError
from .uploads import UploadError, is_upload_id

log = logging.getLogger("kiosk")

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
MAX_JSON_BYTES = 256 * 1024
COOKIE = "kiosk_session"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".png": "image/png",
}
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors {ancestors}"
)
# Uploaded files may be SVG; sandboxed and without scripts they can only ever be pictures.
UPLOAD_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"


class ApiError(Exception):
    def __init__(self, status, message, path=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.path = path


def resolve_static(base, relative):
    """The file for a URL path inside `base`, or None. Never leaves `base`."""
    relative = unquote(relative).lstrip("/")
    if not relative or "\x00" in relative or any(part in ("..", "") for part in relative.split("/")[:-1]):
        return None
    base = base.resolve()
    path = (base / relative).resolve()
    if base not in path.parents or not path.is_file() or path.name.startswith("."):
        return None
    return path


class BaseHandler(BaseHTTPRequestHandler):
    server_version = "kiosk"
    sys_version = ""
    frame_ancestors = "'none'"

    @property
    def kiosk(self):
        return self.server.kiosk

    # Plumbing

    def log_message(self, format, *args):
        log.debug("%s %s", self.address_string(), format % args)

    def _headers(self, status, content_type, length, extra=None, csp=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Security-Policy", csp or CSP.format(ancestors=self.frame_ancestors))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        if "Cache-Control" not in (extra or {}):
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def send_json(self, payload, status=HTTPStatus.OK, extra=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body), {"Cache-Control": "no-store", **(extra or {})})
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_error_json(self, status, message, path=None, extra=None):
        error = {"message": message}
        if path:
            error["path"] = path
        self.send_json({"error": error}, status, extra)

    def send_file(self, path, content_type=None, extra=None, csp=None):
        data = path.read_bytes()
        content_type = content_type or CONTENT_TYPES.get(path.suffix, "application/octet-stream")
        self._headers(HTTPStatus.OK, content_type, len(data), extra, csp)
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_static(self, base, relative):
        path = resolve_static(base, relative)
        if path is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden.")
        self.send_file(path)

    def send_upload(self, upload_id):
        path = self.kiosk.uploads.path(upload_id) if is_upload_id(upload_id) else None
        if path is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden.")
        kind = upload_id.rsplit(".", 1)[1]
        content_type = {"jpg": "image/jpeg", "svg": "image/svg+xml"}.get(kind, f"image/{kind}")
        # The id is a content hash: the file behind it never changes.
        self.send_file(path, content_type, {"Cache-Control": "public, max-age=31536000, immutable"}, csp=UPLOAD_CSP)

    def read_body(self, limit):
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError as err:
            raise ApiError(HTTPStatus.LENGTH_REQUIRED, "Die Anfrage hat keine Länge.") from err
        if length < 0 or length > limit:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Die Anfrage ist zu groß.")
        return self.rfile.read(length)

    def read_json(self):
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Erwartet wird JSON.")
        try:
            payload = json.loads(self.read_body(MAX_JSON_BYTES) or b"null")
        except ValueError as err:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Die Anfrage ist kein gültiges JSON.") from err
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Erwartet wird ein JSON-Objekt.")
        return payload

    def _dispatch(self):
        url = urlsplit(self.path)
        try:
            self.route(url.path, parse_qs(url.query))
        except ApiError as err:
            self.send_error_json(err.status, err.message, err.path)
        except AuthError as err:
            extra = {"Retry-After": str(err.retry_after)} if err.retry_after else None
            self.send_error_json(err.status, err.message, extra=extra)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:  # noqa: BLE001 - the user gets a message, the log gets the details
            log.exception("Request %s %s failed", self.command, url.path)
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Interner Fehler. Details stehen im Log des Kiosk-Dienstes.")

    def do_GET(self):
        self._dispatch()

    def do_HEAD(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()

    def require_get(self):
        if self.command not in ("GET", "HEAD"):
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Diese Methode ist hier nicht erlaubt.")

    def screen_routes(self, path, query, local):
        """Shared by the screen port and the preview inside the admin port. True if handled."""
        if path == "/api/state":
            self.require_get()
            self.send_json(self.kiosk.state(include_setup=local))
        elif path == "/api/revision":
            self.require_get()
            if local:
                self.kiosk.record_screen(query.get("w", [""])[0], query.get("h", [""])[0])
            self.send_json(self.kiosk.revision())
        elif path == "/api/health":
            self.send_json({"ok": True})
        elif path.startswith("/uploads/"):
            self.require_get()
            self.send_upload(path[len("/uploads/"):])
        else:
            return False
        return True


class ScreenHandler(BaseHandler):
    """127.0.0.1 only: the screen itself. No login, nothing that changes state."""

    def route(self, path, query):
        if self.screen_routes(path, query, local=True):
            return
        self.require_get()
        if path.startswith("/api/"):
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden.")
        if path.startswith("/shared/"):
            self.send_static(WEB_DIR / "shared", path[len("/shared/"):])
        else:
            self.send_static(WEB_DIR / "screen", path if path != "/" else "index.html")


class AdminHandler(BaseHandler):
    """The local network: admin interface, admin API and a preview of the screen."""

    frame_ancestors = "'self'"

    def _token(self):
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        morsel = cookie.get(COOKIE)
        return morsel.value if morsel else None

    def _authenticated(self):
        return self.kiosk.auth.session_valid(self._token())

    def _require_login(self):
        if not self._authenticated():
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Bitte anmelden.")

    def _require_same_origin(self):
        # Against cross-site requests: browsers always send Origin on POST, PUT and DELETE.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host")
        if not origin or not host or urlsplit(origin).netloc != host:
            raise ApiError(HTTPStatus.FORBIDDEN, "Anfrage von einer fremden Seite abgelehnt.")

    def _session_cookie(self, token):
        return {"Set-Cookie": f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_MAX_SECONDS}"}

    def route(self, path, query):
        if path.startswith("/api/admin/"):
            if self.command not in ("GET", "HEAD"):
                self._require_same_origin()
            self.admin_api(path[len("/api/admin/"):])
            return
        if path.startswith("/screen/api/") or path.startswith("/uploads/"):
            self._require_login()
            if path.startswith("/screen/"):
                path = path[len("/screen"):]
            if self.screen_routes(path, query, local=False):
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden.")
        self.require_get()
        if path.startswith("/api/"):
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden.")
        if path.startswith("/shared/"):
            self.send_static(WEB_DIR / "shared", path[len("/shared/"):])
        elif path == "/screen":
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", "/screen/")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path.startswith("/screen/"):
            relative = path[len("/screen/"):] or "index.html"
            self.send_static(WEB_DIR / "screen", relative)
        else:
            self.send_static(WEB_DIR / "admin", path if path != "/" else "index.html")

    def admin_api(self, name):
        kiosk = self.kiosk
        address = self.client_address[0]
        method = self.command

        if name == "session" and method == "GET":
            self.send_json({"authenticated": self._authenticated(), "setupRequired": kiosk.auth.setup_required})
            return
        if name == "setup" and method == "POST":
            payload = self.read_json()
            token = kiosk.auth.setup(payload.get("code"), payload.get("password"), address)
            self.send_json({"ok": True}, extra=self._session_cookie(token))
            return
        if name == "login" and method == "POST":
            payload = self.read_json()
            token = kiosk.auth.login(payload.get("password"), address)
            self.send_json({"ok": True}, extra=self._session_cookie(token))
            return
        if name == "logout" and method == "POST":
            kiosk.auth.logout(self._token())
            self.send_json({"ok": True}, extra={"Set-Cookie": f"{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})
            return

        self._require_login()

        if name == "settings" and method == "GET":
            settings, revision = kiosk.settings.get()
            self.send_json({"settings": settings, "revision": revision})
        elif name == "settings" and method == "PUT":
            payload = self.read_json()
            try:
                settings, revision = kiosk.settings.update(payload.get("settings"), payload.get("revision"), kiosk.uploads.ids())
            except SettingsError as err:
                raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, err.message, err.path) from err
            except ConflictError:
                settings, revision = kiosk.settings.get()
                self.send_json({"error": {"message": "Jemand anderes hat die Einstellungen gerade geändert. Der aktuelle Stand ist geladen."},
                                "settings": settings, "revision": revision}, HTTPStatus.CONFLICT)
                return
            self.send_json({"settings": settings, "revision": revision})
        elif name == "uploads" and method == "GET":
            self.send_json({"uploads": kiosk.uploads_with_usage()})
        elif name == "uploads" and method == "POST":
            data = self.read_body(8 * 1024 * 1024 + 1)
            try:
                item = kiosk.uploads.add(data, unquote(self.headers.get("X-File-Name", "")))
            except UploadError as err:
                raise ApiError(err.status, err.message) from err
            self.send_json({"upload": item}, HTTPStatus.CREATED)
        elif name.startswith("uploads/") and method == "DELETE":
            upload_id = name[len("uploads/"):]
            used_by = kiosk.upload_usage().get(upload_id)
            if used_by:
                raise ApiError(HTTPStatus.CONFLICT, f"Das Bild wird noch verwendet: {', '.join(used_by)}. Bitte zuerst dort entfernen.")
            try:
                kiosk.uploads.remove(upload_id)
            except UploadError as err:
                raise ApiError(err.status, err.message) from err
            self.send_json({"ok": True})
        elif name == "status" and method == "GET":
            self.send_json(kiosk.status())
        elif name == "actions/refresh" and method == "POST":
            kiosk.refresh_now()
            self.send_json({"ok": True})
        elif name == "actions/reload-screen" and method == "POST":
            kiosk.reload_screen()
            self.send_json({"ok": True})
        elif name == "password" and method == "POST":
            payload = self.read_json()
            token = kiosk.auth.change_password(payload.get("current"), payload.get("new"), address)
            self.send_json({"ok": True}, extra=self._session_cookie(token))
        else:
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden.")
