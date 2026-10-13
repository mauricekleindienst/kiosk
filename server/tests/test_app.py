import tempfile
import unittest
from pathlib import Path

from kiosk.app import RETRY_SECONDS
from kiosk.config import ConfigError, load_config
from kiosk.store import Store

from helpers import PNG, make_kiosk


def news_of(state, widget_id):
    return state["widgets"][widget_id]


class KioskTest(unittest.TestCase):
    def setUp(self):
        self.kiosk = make_kiosk(self)
        self.upstream = self.kiosk.upstream

    def change(self, mutate):
        settings, revision = self.kiosk.settings.get()
        mutate(settings)
        return self.kiosk.settings.update(settings, revision, self.kiosk.uploads.ids())

    def test_first_run_fills_every_source(self):
        self.kiosk.run_due(0)
        state = self.kiosk.state()
        self.assertEqual(state["weather"]["data"]["location"], "Kassel")
        self.assertEqual(state["weather"]["fetchedAt"], self.kiosk.clock.now.isoformat())
        main = news_of(state, "news-main")
        self.assertEqual(main["data"][0]["title"], "Rheinmetall erhält Großauftrag für Munition")
        self.assertEqual(len(news_of(state, "news-side")["data"]), 3, "the server keeps more than a widget shows")
        self.assertEqual(state["settings"]["display"]["reloadAt"], "03:30")
        self.assertIsNone(state["setup"], "the setup code only goes to the local screen")

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
        kiosk = make_kiosk(self, upstream=self.upstream)
        with self.assertLogs("kiosk", "ERROR"):
            kiosk.run_due(0)
        self.assertIsNotNone(kiosk.state()["weather"]["error"])
        self.assertIsNotNone(news_of(kiosk.state(), "news-main")["data"], "the other sources still refresh")

    def test_garbage_feed_is_reported_not_raised(self):
        self.upstream.fetch = lambda url, accept="*/*": b"<html>Bitte Cookies akzeptieren</html>"
        kiosk = make_kiosk(self, upstream=self.upstream)
        kiosk.run_due(0)
        self.assertIn("unknown feed format", news_of(kiosk.state(), "news-main")["error"])

    def test_a_changed_feed_is_fetched_right_away(self):
        self.kiosk.run_due(0)
        url = "https://example.org/feed.xml"

        def edit(settings):
            settings["widgets"][2]["options"]["url"] = url

        self.change(edit)
        self.kiosk.run_due(1)
        self.assertIn(url, self.upstream.requests)
        self.assertIsNotNone(news_of(self.kiosk.state(), "news-side")["data"])

    def test_widgets_with_the_same_feed_share_one_source(self):
        def same(settings):
            settings["widgets"][2]["options"]["url"] = settings["widgets"][1]["options"]["url"]

        self.change(same)
        self.kiosk.run_due(0)
        self.assertEqual(len([url for url in self.upstream.requests if "news.google" in url]), 1)

    def test_moving_the_location_fetches_new_weather(self):
        self.kiosk.run_due(0)

        def move(settings):
            settings["location"] = {"name": "Unterlüß", "lat": 52.83, "lon": 10.28}

        self.change(move)
        self.assertIsNone(self.kiosk.state()["weather"]["data"], "old weather must not be shown for the new place")
        self.kiosk.run_due(1)
        self.assertEqual(self.kiosk.state()["weather"]["data"]["location"], "Unterlüß")

    def test_refresh_now_and_reload_screen(self):
        self.kiosk.run_due(0)
        count = len(self.upstream.requests)
        self.kiosk.refresh_now()
        self.kiosk.run_due(1)
        self.assertGreater(len(self.upstream.requests), count)
        before = self.kiosk.revision()["reload"]
        self.kiosk.reload_screen()
        self.assertEqual(self.kiosk.revision()["reload"], before + 1)

    def test_data_version_tells_the_screen_to_fetch(self):
        before = self.kiosk.revision()["data"]
        self.kiosk.run_due(0)
        self.assertGreater(self.kiosk.revision()["data"], before)

    def test_cache_survives_a_restart_without_network(self):
        self.kiosk.run_due(0)
        self.upstream.failing.update({"brightsky", "news.google"})
        restarted = make_kiosk(self, upstream=self.upstream)
        restarted.store = Store(self.kiosk.root / "cache")
        restarted._apply(restarted.settings.get()[0])
        restarted.run_due(0)
        state = restarted.state()
        self.assertEqual(state["weather"]["data"]["location"], "Kassel")
        self.assertIsNotNone(state["weather"]["error"])
        self.assertEqual(len(news_of(state, "news-main")["data"]), 3)

    def test_corrupt_cache_file_is_ignored(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        Path(folder.name, "weather.json").write_text("{not json", encoding="utf-8")
        store = Store(folder.name)
        with self.assertLogs("kiosk", "WARNING"):
            store.load(["weather"])
        self.assertEqual(store.snapshot(), {})

    def test_upload_usage_names_the_places(self):
        item = self.kiosk.uploads.add(PNG, "logo.png")

        def use(settings):
            settings["logo"] = item["id"]
            settings["widgets"][3].update(y=1, h=7)
            settings["widgets"].append({"id": "logo", "type": "logo", "x": 7, "y": 0, "w": 1, "h": 1,
                                        "options": {"image": item["id"]}})

        self.change(use)
        self.assertEqual(self.kiosk.upload_usage()[item["id"]], ["Firmenlogo", "Kachel „Logo“"])

    def add_widgets(self, *widgets):
        def mutate(settings):
            settings["widgets"][3].update(y=4, h=4)
            settings["widgets"].extend(widgets)

        return self.change(mutate)

    def test_stock_and_transit_widgets_get_their_data(self):
        stop = {"id": "8000193", "name": "Kassel Hbf"}
        self.add_widgets(
            {"id": "stock", "type": "stock", "x": 7, "y": 0, "w": 5, "h": 2, "options": {}},
            {"id": "transit", "type": "transit", "x": 7, "y": 2, "w": 5, "h": 2, "options": {"stop": stop, "products": ["tram", "bus"]}},
        )
        self.kiosk.run_due(0)
        state = self.kiosk.state()
        self.assertEqual(state["widgets"]["stock"]["data"]["price"], 1848.5)
        self.assertEqual(state["widgets"]["stock"]["refreshMinutes"], 5)
        self.assertEqual(state["widgets"]["transit"]["data"][0]["line"], "Bus 16")
        transit_requests = [url for url in self.upstream.requests if "/departures" in url]
        self.assertEqual(len(transit_requests), 1)
        self.assertIn("tram=true", transit_requests[0])
        self.assertIn("regional=false", transit_requests[0])
        labels = [source["label"] for source in self.kiosk.status()["sources"]]
        self.assertIn("Aktie RHM.DE", labels)
        self.assertIn("Abfahrten Kassel Hbf", labels)

    def test_a_transit_tile_without_a_stop_fetches_nothing(self):
        self.add_widgets({"id": "transit", "type": "transit", "x": 7, "y": 0, "w": 5, "h": 4, "options": {}})
        self.kiosk.run_due(0)
        self.assertNotIn("transit", self.kiosk.state()["widgets"])
        self.assertFalse([url for url in self.upstream.requests if "/departures" in url])

    def test_display_follows_the_night_schedule(self):
        def night(settings):
            settings["display"]["sleep"].update(enabled=True, **{"from": "09:00", "to": "10:00"})

        self.assertEqual(self.kiosk.display(), {"on": True, "powerOff": True, "cec": False})
        self.change(night)
        self.assertEqual(self.kiosk.display()["on"], False, "9:41 is inside 9-10")

    def test_nightly_update_is_started_at_its_time(self):
        started = []
        self.kiosk.updater = type("FakeUpdater", (), {
            "due": lambda _self, settings, local: local.strftime("%H:%M") == settings["updates"]["time"],
            "start": lambda _self: started.append(True),
            "status": {},
        })()

        def at_941(settings):
            settings["updates"]["time"] = "09:41"

        self.kiosk.tick()
        self.assertEqual(started, [])
        self.change(at_941)
        self.kiosk.tick()
        self.assertEqual(started, [True])

    def test_status_lists_sources_and_screen(self):
        self.kiosk.run_due(0)
        self.kiosk.record_screen("1920", "1080")
        status = self.kiosk.status()
        self.assertEqual([source["label"] for source in status["sources"]],
                         ["Wetter für Kassel", "Nachrichten „Rheinmetall“", "Nachrichten „Kassel und Region“"])
        self.assertEqual((status["screen"]["width"], status["screen"]["height"]), (1920, 1080))
        self.kiosk.record_screen("abc", "1")
        self.assertEqual(self.kiosk.status()["screen"]["width"], 1920, "garbage sizes are ignored")


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
        config = load_config("/nonexistent/config.json")
        self.assertEqual((config["port"], config["adminPort"]), (8080, 8081))

    def test_invalid_files_name_the_problem(self):
        with self.assertRaisesRegex(ConfigError, "not valid JSON"):
            load_config(self.write("{"))
        with self.assertRaisesRegex(ConfigError, "http"):
            load_config(self.write('{"news": {"side": {"url": "file:///etc/passwd"}}}'))
        with self.assertRaisesRegex(ConfigError, "reloadAt"):
            load_config(self.write('{"display": {"reloadAt": "25:00"}}'))
        with self.assertRaisesRegex(ConfigError, "lat"):
            load_config(self.write('{"location": {"lat": 120}}'))
        with self.assertRaisesRegex(ConfigError, "adminPort"):
            load_config(self.write('{"adminPort": "8081"}'))

    def test_admin_interface_can_be_switched_off(self):
        self.assertIsNone(load_config(self.write('{"adminPort": null}'))["adminPort"])


if __name__ == "__main__":
    unittest.main()
