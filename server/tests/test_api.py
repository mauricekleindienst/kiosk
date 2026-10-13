import json
import threading
import unittest
import urllib.error
import urllib.request

from kiosk.http_api import AdminHandler, ScreenHandler
from kiosk.app import make_server

from helpers import PNG, make_kiosk

NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Client:
    def __init__(self, base):
        self.base = base
        self.cookie = None

    def request(self, method, path, body=None, headers=None, origin=True, raw=False):
        headers = dict(headers or {})
        data = None
        if body is not None and not raw:
            data = json.dumps(body).encode()
            headers.setdefault("Content-Type", "application/json")
        elif raw:
            data = body
        if origin is True:
            headers.setdefault("Origin", self.base)
        elif origin:
            headers["Origin"] = origin
        if self.cookie:
            headers["Cookie"] = self.cookie
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with NO_PROXY.open(request, timeout=10) as response:
                status, response_headers, payload = response.status, response.headers, response.read()
        except urllib.error.HTTPError as err:
            status, response_headers, payload = err.code, err.headers, err.read()
            err.close()
        cookie = response_headers.get("Set-Cookie")
        if cookie:
            self.cookie = cookie.split(";", 1)[0]
        content_type = response_headers.get("Content-Type", "")
        parsed = json.loads(payload) if content_type.startswith("application/json") else payload
        return status, response_headers, parsed


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.kiosk = make_kiosk(self)
        self.kiosk.run_due(0)
        self.screen_server = make_server(self.kiosk, "127.0.0.1", 0, ScreenHandler)
        self.admin_server = make_server(self.kiosk, "127.0.0.1", 0, AdminHandler)
        self.kiosk.admin_port = self.admin_server.server_address[1]
        for server in (self.screen_server, self.admin_server):
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        self.screen = Client(f"http://127.0.0.1:{self.screen_server.server_address[1]}")
        self.admin = Client(f"http://127.0.0.1:{self.kiosk.admin_port}")

    def sign_up(self):
        status, _, _ = self.admin.request("POST", "/api/admin/setup", {"code": self.kiosk.auth.setup_code, "password": "richtig-gut"})
        self.assertEqual(status, 200)

    # Screen port

    def test_screen_state_shows_the_setup_code_locally(self):
        status, headers, state = self.screen.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(state["setup"]["code"], self.kiosk.auth.setup_code)
        self.assertTrue(all(url.endswith(f":{self.kiosk.admin_port}") for url in state["setup"]["urls"]))
        self.assertEqual(state["widgets"]["news-main"]["data"][0]["source"], "Handelsblatt")
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_screen_revision_records_the_screen_size(self):
        status, _, revision = self.screen.request("GET", "/api/revision?w=1920&h=1080")
        self.assertEqual(status, 200)
        self.assertEqual(set(revision), {"settings", "data", "reload", "setup", "build"})
        self.assertEqual(self.kiosk.status()["screen"]["width"], 1920)

    def test_screen_port_has_no_admin_api_and_no_writes(self):
        self.assertEqual(self.screen.request("GET", "/api/admin/session")[0], 404)
        self.assertEqual(self.screen.request("POST", "/api/state", {})[0], 405)

    def test_screen_page_and_shared_files(self):
        status, headers, body = self.screen.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'<html lang="de">', body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", headers["Content-Security-Policy"])
        self.assertEqual(self.screen.request("GET", "/js/main.js")[1]["Content-Type"], "text/javascript; charset=utf-8")
        self.assertEqual(self.screen.request("GET", "/shared/widgets.json")[0], 200)

    def test_no_escape_from_the_web_folders(self):
        for client in (self.screen, self.admin):
            for path in ("/../config.default.json", "/%2e%2e/config.default.json", "/shared/../../server/kiosk/auth.py",
                         "/shared/%2e%2e/%2e%2e/config.default.json", "/js/", "/uploads/../admin.json"):
                with self.subTest(client=client.base, path=path):
                    self.assertIn(client.request("GET", path)[0], (401, 404))

    # Admin port: access

    def test_setup_then_login(self):
        status, _, session = self.admin.request("GET", "/api/admin/session")
        self.assertEqual(session, {"authenticated": False, "setupRequired": True})
        status, _, body = self.admin.request("POST", "/api/admin/setup", {"code": "x", "password": "richtig-gut"})
        self.assertEqual(status, 401)
        self.assertIn("Code", body["error"]["message"])
        self.sign_up()
        self.assertIn("HttpOnly", self.admin.request("POST", "/api/admin/logout", {})[1]["Set-Cookie"])
        self.assertEqual(self.admin.request("GET", "/api/admin/settings")[0], 401)
        status, headers, _ = self.admin.request("POST", "/api/admin/login", {"password": "richtig-gut"})
        self.assertEqual(status, 200)
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertEqual(self.admin.request("GET", "/api/admin/session")[2]["authenticated"], True)
        self.assertIsNone(self.screen.request("GET", "/api/state")[2]["setup"], "the code disappears from the screen")

    def test_everything_but_the_login_needs_a_session(self):
        for method, path in (("GET", "/api/admin/settings"), ("PUT", "/api/admin/settings"), ("GET", "/api/admin/uploads"),
                             ("GET", "/api/admin/status"), ("POST", "/api/admin/actions/refresh"),
                             ("GET", "/screen/api/state"), ("GET", "/uploads/0123456789abcdef0123.png")):
            with self.subTest(path=path):
                self.assertEqual(self.admin.request(method, path, {} if method != "GET" else None)[0], 401)

    def test_cross_site_writes_are_refused(self):
        self.sign_up()
        settings = self.admin.request("GET", "/api/admin/settings")[2]
        for origin in (None, "http://evil.example"):
            status, _, body = self.admin.request("PUT", "/api/admin/settings", settings, origin=origin or False)
            self.assertEqual(status, 403, origin)
        status, _, _ = self.admin.request("POST", "/api/admin/login", b"password=x", raw=True,
                                          headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 415, "form posts from other sites never reach the login")

    def test_lockout_answers_with_retry_after(self):
        self.sign_up()
        self.admin.cookie = None
        for _ in range(5):
            self.admin.request("POST", "/api/admin/login", {"password": "falsch-falsch"})
        status, headers, body = self.admin.request("POST", "/api/admin/login", {"password": "falsch-falsch"})
        self.assertEqual(status, 429)
        self.assertTrue(int(headers["Retry-After"]) > 0)

    # Admin port: settings, uploads, actions

    def test_settings_round_trip_conflict_and_errors(self):
        self.sign_up()
        body = self.admin.request("GET", "/api/admin/settings")[2]
        settings, revision = body["settings"], body["revision"]
        settings["location"]["name"] = "Unterlüß"
        status, _, saved = self.admin.request("PUT", "/api/admin/settings", {"settings": settings, "revision": revision})
        self.assertEqual((status, saved["revision"]), (200, revision + 1))
        self.assertEqual(self.screen.request("GET", "/api/revision")[2]["settings"], revision + 1)

        status, _, conflict = self.admin.request("PUT", "/api/admin/settings", {"settings": settings, "revision": revision})
        self.assertEqual(status, 409)
        self.assertEqual(conflict["settings"]["location"]["name"], "Unterlüß")

        settings["widgets"][0]["w"] = 20
        status, _, error = self.admin.request("PUT", "/api/admin/settings", {"settings": settings, "revision": revision + 1})
        self.assertEqual(status, 422)
        self.assertEqual(error["error"]["path"], "widgets.0.x")

    def test_logo_upload_use_and_delete(self):
        self.sign_up()
        status, _, body = self.admin.request("POST", "/api/admin/uploads", PNG, raw=True,
                                             headers={"Content-Type": "image/png", "X-File-Name": "Logo%20Firma.png"})
        self.assertEqual(status, 201)
        upload = body["upload"]
        self.assertEqual(upload["name"], "Logo Firma.png")

        status, headers, data = self.admin.request("GET", f"/uploads/{upload['id']}")
        self.assertEqual((status, data), (200, PNG))
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        self.assertEqual(self.screen.request("GET", f"/uploads/{upload['id']}")[0], 200)

        current = self.admin.request("GET", "/api/admin/settings")[2]
        current["settings"]["logo"] = upload["id"]
        self.assertEqual(self.admin.request("PUT", "/api/admin/settings", current)[0], 200)
        status, _, body = self.admin.request("DELETE", f"/api/admin/uploads/{upload['id']}")
        self.assertEqual(status, 409)
        self.assertIn("Firmenlogo", body["error"]["message"])
        self.assertEqual(self.admin.request("GET", "/api/admin/uploads")[2]["uploads"][0]["usedBy"], ["Firmenlogo"])

        current = self.admin.request("GET", "/api/admin/settings")[2]
        current["settings"]["logo"] = None
        self.admin.request("PUT", "/api/admin/settings", current)
        self.assertEqual(self.admin.request("DELETE", f"/api/admin/uploads/{upload['id']}")[0], 200)

    def test_upload_rejects_non_images(self):
        self.sign_up()
        status, _, body = self.admin.request("POST", "/api/admin/uploads", b"<html><script>alert(1)</script>", raw=True,
                                             headers={"Content-Type": "image/png"})
        self.assertEqual(status, 415)
        self.assertIn("PNG", body["error"]["message"])

    def test_actions_status_and_password(self):
        self.sign_up()
        self.assertEqual(self.admin.request("POST", "/api/admin/actions/reload-screen", {})[0], 200)
        self.assertEqual(self.screen.request("GET", "/api/revision")[2]["reload"], 1)
        status = self.admin.request("GET", "/api/admin/status")[2]
        self.assertEqual(status["sources"][0]["label"], "Wetter für Kassel")
        self.assertEqual(self.admin.request("POST", "/api/admin/password", {"current": "falsch-falsch", "new": "neues-passwort"})[0], 400)
        self.assertEqual(self.admin.request("POST", "/api/admin/password", {"current": "richtig-gut", "new": "neues-passwort"})[0], 200)
        self.assertEqual(self.admin.request("GET", "/api/admin/settings")[0], 200, "the one who changed it stays signed in")

    def test_preview_of_the_screen_inside_the_admin(self):
        self.sign_up()
        status, headers, body = self.admin.request("GET", "/screen/")
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'self'", headers["Content-Security-Policy"])
        state = self.admin.request("GET", "/screen/api/state")[2]
        self.assertIsNone(state["setup"])
        self.admin.request("GET", "/screen/api/revision?w=300&h=200")
        self.assertIsNone(self.kiosk.status()["screen"], "the preview does not pose as the real screen")

    def test_display_state_only_on_the_screen_port(self):
        status, _, display = self.screen.request("GET", "/api/display")
        self.assertEqual((status, display), (200, {"on": True, "powerOff": True, "cec": False}))
        self.sign_up()
        self.assertEqual(self.admin.request("GET", "/api/display")[0], 404)

    def test_stop_search_needs_login_and_two_letters(self):
        self.assertEqual(self.admin.request("GET", "/api/admin/transit/stops?query=Kassel")[0], 401)
        self.sign_up()
        self.assertEqual(self.admin.request("GET", "/api/admin/transit/stops?query=K")[0], 400)
        status, _, body = self.admin.request("GET", "/api/admin/transit/stops?query=Kassel%20Hbf")
        self.assertEqual(status, 200)
        self.assertEqual(body["stops"][0], {"id": "8000193", "name": "Kassel Hbf"})
        self.kiosk.upstream.failing.add("/locations")
        status, _, body = self.admin.request("GET", "/api/admin/transit/stops?query=Kassel")
        self.assertEqual(status, 502)
        self.assertIn("Fahrplanauskunft", body["error"]["message"])

    def test_update_check_runs_once_at_a_time(self):
        self.sign_up()
        calls = []

        class FakeUpdater:
            status = {}

            def start(self):
                calls.append(1)
                return len(calls) == 1

        self.kiosk.updater = FakeUpdater()
        self.assertEqual(self.admin.request("POST", "/api/admin/updates/check", {})[0], 202)
        self.assertEqual(self.admin.request("POST", "/api/admin/updates/check", {})[0], 409)
        self.assertEqual(self.admin.request("POST", "/api/admin/updates/check", {}, origin="http://evil.example")[0], 403)

    def test_admin_page_is_served(self):
        status, headers, body = self.admin.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'<html lang="de" data-app="admin">', body)
        self.assertIn("frame-ancestors 'self'", headers["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()
