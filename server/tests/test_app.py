import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from kiosk import http_client
from kiosk.app import RETRY_SECONDS, Kiosk, make_server
from kiosk.config import ConfigError, load_config
from kiosk.store import Store

from helpers import berlin, fixture_bytes, fixture_json, forecast

NOW = berlin(2026, 10, 13, 9, 41)


class FakeUpstream:
    """Answers the kiosk's requests like Bright Sky and Google News would, or fails on demand."""

    def __init__(self):
        self.failing = set()
        self.requests = []

    def _check(self, url):
        self.requests.append(url)
        for part in self.failing:
            if part in url:
                raise http_client.FetchError(f"{url} is not reachable: fake outage")

    def fetch(self, url, accept="*/*"):
        self._check(url)
        return fixture_bytes("google-news-rheinmetall.xml")

    def fetch_json(self, url):
        self._check(url)
        if "/current_weather" in url:
            return fixture_json("brightsky-current.json")
        if "/alerts" in url:
            return fixture_json("brightsky-alerts.json")
        return forecast(berlin(2026, 10, 13, 0), 24 * 8)


class KioskTest(unittest.TestCase):
    def setUp(self):
        self.cache = tempfile.TemporaryDirectory()
        self.addCleanup(self.cache.cleanup)
        self.upstream = FakeUpstream()
        self.kiosk = self.make_kiosk()

    def make_kiosk(self):
        return Kiosk(load_config(None), Store(self.cache.name), self.upstream.fetch, self.upstream.fetch_json, lambda: NOW)

    def test_first_run_fills_every_source(self):
        self.kiosk.run_due(0)
        state = self.kiosk.state()
        self.assertEqual(state["weather"]["data"]["location"], "Kassel")
        self.assertEqual(state["weather"]["fetchedAt"], NOW.isoformat())
        self.assertEqual(state["news"]["main"]["title"], "Rheinmetall")
        self.assertEqual(state["news"]["main"]["data"][0]["title"], "Rheinmetall erhält Großauftrag für Munition")
        self.assertEqual(len(state["news"]["side"]["data"]), 2, "the default limit of the regional block")
        self.assertEqual(state["display"]["reloadAt"], "03:30")

    def test_sources_are_not_refetched_before_their_interval(self):
        self.kiosk.run_due(0)
        count = len(self.upstream.requests)
        self.kiosk.run_due(60)
        self.assertEqual(len(self.upstream.requests), count)
        self.kiosk.run_due(10 * 60)
        self.assertGreater(len(self.upstream.requests), count)

    def test_failure_keeps_last_good_data_and_retries_sooner(self):
        self.kiosk.run_due(0)
        self.upstream.failing.add("brightsky")
        self.kiosk.run_due(10 * 60)
        weather = self.kiosk.state()["weather"]
        self.assertEqual(weather["data"]["location"], "Kassel", "last good data must survive a failed refresh")
        self.assertIn("fake outage", weather["error"])

        self.upstream.failing.clear()
        self.kiosk.run_due(10 * 60 + RETRY_SECONDS)
        self.assertIsNone(self.kiosk.state()["weather"]["error"])

    def test_failing_alerts_do_not_hide_the_forecast(self):
        self.upstream.failing.add("/alerts")
        self.kiosk.run_due(0)
        weather = self.kiosk.state()["weather"]
        self.assertIsNone(weather["error"])
        self.assertEqual(weather["data"]["alerts"], [])

    def test_unexpected_answer_shape_does_not_stop_the_scheduler(self):
        self.upstream.fetch_json = lambda url: ["not", "an", "object"]
        self.kiosk = self.make_kiosk()
        with self.assertLogs("kiosk", "ERROR"):
            self.kiosk.run_due(0)
        self.assertIsNotNone(self.kiosk.state()["weather"]["error"])
        self.assertIsNotNone(self.kiosk.state()["news"]["main"]["data"], "the other sources still refresh")

    def test_garbage_feed_is_reported_not_raised(self):
        self.upstream.fetch = lambda url, accept="*/*": b"<html>Bitte Cookies akzeptieren</html>"
        self.kiosk = self.make_kiosk()
        self.kiosk.run_due(0)
        self.assertIn("unknown feed format", self.kiosk.state()["news"]["main"]["error"])

    def test_cache_survives_a_restart_without_network(self):
        self.kiosk.run_due(0)
        self.upstream.failing.update({"brightsky", "news.google"})
        restarted = self.make_kiosk()
        restarted.store.load(restarted.sources)
        restarted.run_due(0)
        state = restarted.state()
        self.assertEqual(state["weather"]["data"]["location"], "Kassel")
        self.assertEqual(state["weather"]["fetchedAt"], NOW.isoformat())
        self.assertIsNotNone(state["weather"]["error"])
        self.assertEqual(len(state["news"]["main"]["data"]), 3)

    def test_corrupt_cache_file_is_ignored(self):
        Path(self.cache.name, "weather.json").write_text("{not json", encoding="utf-8")
        store = Store(self.cache.name)
        with self.assertLogs("kiosk", "WARNING"):
            store.load(["weather"])
        self.assertEqual(store.snapshot(), {})

    def test_cache_write_leaves_no_temp_files(self):
        self.kiosk.run_due(0)
        self.assertEqual(sorted(p.name for p in Path(self.cache.name).iterdir()),
                         ["news-main.json", "news-side.json", "weather.json"])


class ConfigTest(unittest.TestCase):
    def write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def test_owner_file_overrides_single_keys(self):
        config = load_config(self.write('{"location": {"name": "Unterlüß"}, "news": {"main": {"limit": 3}}}'))
        self.assertEqual(config["location"]["name"], "Unterlüß")
        self.assertEqual(config["location"]["lat"], 51.3127)
        self.assertEqual(config["news"]["main"]["limit"], 3)
        self.assertEqual(config["news"]["main"]["title"], "Rheinmetall")

    def test_missing_owner_file_means_defaults(self):
        self.assertEqual(load_config("/nonexistent/config.json")["port"], 8080)

    def test_invalid_files_name_the_problem(self):
        with self.assertRaisesRegex(ConfigError, "not valid JSON"):
            load_config(self.write("{"))
        with self.assertRaisesRegex(ConfigError, "http"):
            load_config(self.write('{"news": {"side": {"url": "file:///etc/passwd"}}}'))
        with self.assertRaisesRegex(ConfigError, "reloadAt"):
            load_config(self.write('{"display": {"reloadAt": "25:00"}}'))
        with self.assertRaisesRegex(ConfigError, "lat"):
            load_config(self.write('{"location": {"lat": 120}}'))


class HttpServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = tempfile.TemporaryDirectory()
        upstream = FakeUpstream()
        kiosk = Kiosk(load_config(None), Store(cls.cache.name), upstream.fetch, upstream.fetch_json, lambda: NOW)
        kiosk.run_due(0)
        cls.server = make_server(kiosk, "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.cache.cleanup()

    def get(self, path):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(self.base + path, timeout=5)

    def test_state_endpoint(self):
        with self.get("/api/state") as response:
            self.assertEqual(response.headers["Content-Type"], "application/json; charset=utf-8")
            state = json.load(response)
        self.assertEqual(state["timeZone"], "Europe/Berlin")
        self.assertEqual(state["weather"]["data"]["daily"][0]["date"], "2026-10-13")

    def test_page_is_served_with_a_strict_csp(self):
        with self.get("/") as response:
            body = response.read().decode("utf-8")
            csp = response.headers["Content-Security-Policy"]
        self.assertIn('<html lang="de">', body)
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe-inline", csp)

    def test_scripts_have_a_module_mime_type(self):
        with self.get("/js/main.js") as response:
            self.assertEqual(response.headers["Content-Type"], "text/javascript")

    def test_no_directory_listing_and_no_escape_from_the_web_folder(self):
        for path in ("/js/", "/api/unknown", "/../config.default.json", "/%2e%2e/config.default.json"):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as caught:
                self.get(path)
            self.assertEqual(caught.exception.code, 404)
            caught.exception.close()


if __name__ == "__main__":
    unittest.main()
