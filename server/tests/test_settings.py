import copy
import json
import tempfile
import unittest
from pathlib import Path

from kiosk.config import load_config
from kiosk.settings import ConflictError, SettingsError, SettingsStore, default_settings, validate

from helpers import CATALOG

DEFAULTS = default_settings(load_config(None), CATALOG)


def with_widget(widget, settings=None):
    settings = copy.deepcopy(settings or DEFAULTS)
    # Make room on the right: the weather column gets shorter.
    settings["widgets"][3].update(y=2, h=6)
    settings["widgets"].append(widget)
    return settings


class ValidateTest(unittest.TestCase):
    def assertInvalid(self, settings, path, message=None, uploads=frozenset()):
        with self.assertRaises(SettingsError) as caught:
            validate(settings, CATALOG, set(uploads))
        self.assertEqual(caught.exception.path, path)
        if message:
            self.assertIn(message, caught.exception.message)

    def test_defaults_reproduce_the_original_layout(self):
        self.assertEqual([(w["id"], w["x"], w["y"], w["w"], w["h"]) for w in DEFAULTS["widgets"]], [
            ("clock", 0, 0, 7, 2), ("news-main", 0, 2, 7, 4), ("news-side", 0, 6, 7, 2), ("weather", 7, 0, 5, 8),
        ])
        self.assertEqual(DEFAULTS["widgets"][2]["options"]["columns"], "2")

    def test_missing_options_get_their_defaults(self):
        settings = with_widget({"id": "msg", "type": "message", "x": 7, "y": 0, "w": 5, "h": 2})
        message = validate(settings, CATALOG, set())["widgets"][-1]
        self.assertEqual(message["options"]["title"], "Herzlich willkommen")
        self.assertEqual(message["options"]["size"], "normal")

    def test_every_widget_type_validates_with_its_defaults(self):
        for kind, spec in CATALOG["types"].items():
            with self.subTest(kind=kind):
                options = {o["key"]: "2026-12-24" for o in spec["options"] if o.get("required") and o["type"] == "date"}
                size = spec["minSize"]
                settings = with_widget({"id": "new", "type": kind, "x": 7, "y": 0, "w": max(size["w"], 1), "h": min(2, 2),
                                        "options": options})
                if size["h"] > 2:
                    settings["widgets"][3].update(y=size["h"], h=8 - size["h"])
                    settings["widgets"][-1]["h"] = size["h"]
                if size["w"] > 5:
                    continue
                validate(settings, CATALOG, set())

    def test_overlap_is_rejected(self):
        settings = with_widget({"id": "msg", "type": "message", "x": 6, "y": 0, "w": 3, "h": 2})
        self.assertInvalid(settings, "widgets.4", "überlappen")

    def test_widget_must_stay_on_the_grid_and_keep_its_minimum_size(self):
        self.assertInvalid(with_widget({"id": "m", "type": "message", "x": 11, "y": 0, "w": 2, "h": 2}), "widgets.4.x", "ragt")
        self.assertInvalid(with_widget({"id": "m", "type": "calendar", "x": 7, "y": 0, "w": 3, "h": 2}), "widgets.4.w", "3 × 3")
        self.assertInvalid(with_widget({"id": "m", "type": "message", "x": -1, "y": 0, "w": 2, "h": 1}), "widgets.4.x")
        self.assertInvalid(with_widget({"id": "m", "type": "message", "x": 7, "y": 0, "w": True, "h": 1}), "widgets.4.w")

    def test_ids_types_and_options_are_checked(self):
        self.assertInvalid(with_widget({"id": "Bad Id", "type": "message", "x": 7, "y": 0, "w": 2, "h": 1}), "widgets.4.id")
        self.assertInvalid(with_widget({"id": "clock", "type": "message", "x": 7, "y": 0, "w": 2, "h": 1}), "widgets", "Kennung")
        self.assertInvalid(with_widget({"id": "m", "type": "iframe", "x": 7, "y": 0, "w": 2, "h": 1}), "widgets.4.type")
        self.assertInvalid(with_widget({"id": "m", "type": "message", "x": 7, "y": 0, "w": 2, "h": 1,
                                        "options": {"script": "x"}}), "widgets.4.options", "Unbekannte")

    def test_option_types(self):
        def news(**options):
            settings = copy.deepcopy(DEFAULTS)
            settings["widgets"][1]["options"].update(options)
            return settings

        self.assertInvalid(news(url="javascript:alert(1)"), "widgets.1.options.url", "http")
        self.assertInvalid(news(url="file:///etc/passwd"), "widgets.1.options.url")
        self.assertInvalid(news(limit=0), "widgets.1.options.limit", "1 bis 12")
        self.assertInvalid(news(limit="5"), "widgets.1.options.limit")
        self.assertInvalid(news(lead="yes"), "widgets.1.options.lead")
        self.assertInvalid(news(columns="3"), "widgets.1.options.columns")
        self.assertInvalid(news(title=""), "widgets.1.options.title", "leer")
        self.assertInvalid(news(title="x" * 61), "widgets.1.options.title", "60")
        self.assertInvalid(news(title="a\nb"), "widgets.1.options.title", "ungültige")
        self.assertEqual(validate(news(title="  Rheinmetall  "), CATALOG, set())["widgets"][1]["options"]["title"], "Rheinmetall")

    def test_dates_zones_and_images(self):
        countdown = {"id": "c", "type": "countdown", "x": 7, "y": 0, "w": 2, "h": 1, "options": {"date": "2026-02-30"}}
        self.assertInvalid(with_widget(countdown), "widgets.4.options.date", "gültiges Datum")
        countdown["options"]["date"] = None
        self.assertInvalid(with_widget(countdown), "widgets.4.options.date", "Datum wählen")

        zones = {"id": "z", "type": "worldclock", "x": 7, "y": 0, "w": 2, "h": 1,
                 "options": {"zones": [{"label": "Mars", "timeZone": "Mars/Olympus"}]}}
        self.assertInvalid(with_widget(zones), "widgets.4.options.zones.0.timeZone", "unbekannt")

        logo = {"id": "l", "type": "logo", "x": 7, "y": 0, "w": 2, "h": 1, "options": {"image": "0123456789abcdef0123.png"}}
        self.assertInvalid(with_widget(logo), "widgets.4.options.image", "gibt es nicht mehr")
        validate(with_widget(logo), CATALOG, {"0123456789abcdef0123.png"})

        slides = {"id": "s", "type": "slideshow", "x": 7, "y": 0, "w": 2, "h": 2,
                  "options": {"images": ["0123456789abcdef0123.png"] * 2}}
        self.assertInvalid(with_widget(slides), "widgets.4.options.images", "einmal", {"0123456789abcdef0123.png"})

    def test_global_settings(self):
        def global_(**changes):
            settings = copy.deepcopy(DEFAULTS)
            for path, value in changes.items():
                target = settings
                *parents, last = path.split("__")
                for parent in parents:
                    target = target[parent]
                target[last] = value
            return settings

        self.assertInvalid(global_(location__lat=91), "location.lat")
        self.assertInvalid(global_(location__name=""), "location.name")
        self.assertInvalid(global_(timeZone="Europe/Kassel"), "timeZone")
        self.assertInvalid(global_(appearance__scale=200), "appearance.scale")
        self.assertInvalid(global_(appearance__density="huge"), "appearance.density")
        self.assertInvalid(global_(display__reloadAt="3:30"), "display.reloadAt")
        self.assertInvalid(global_(display__sleep__from="24:00"), "display.sleep.from")
        self.assertInvalid(global_(logo="0123456789abcdef0123.png"), "logo")
        self.assertInvalid(global_(extra=1), "", "Unbekannte")

    def test_too_many_widgets(self):
        settings = copy.deepcopy(DEFAULTS)
        settings["widgets"] = [{"id": f"m{i}", "type": "message", "x": 0, "y": 0, "w": 2, "h": 1} for i in range(25)]
        self.assertInvalid(settings, "widgets", "24")


class SettingsStoreTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name, "settings.json")

    def test_save_load_and_revision(self):
        store = SettingsStore(self.path, CATALOG, DEFAULTS)
        settings, revision = store.get()
        self.assertEqual(revision, 0)
        settings["location"]["name"] = "Unterlüß"
        seen = []
        store.on_change(seen.append)
        _, revision = store.update(settings, 0, set())
        self.assertEqual(revision, 1)
        self.assertEqual(seen[0]["location"]["name"], "Unterlüß")

        reloaded = SettingsStore(self.path, CATALOG, DEFAULTS)
        self.assertEqual(reloaded.get()[0]["location"]["name"], "Unterlüß")
        self.assertEqual(reloaded.revision, 1)

    def test_stale_revision_is_a_conflict_and_changes_nothing(self):
        store = SettingsStore(self.path, CATALOG, DEFAULTS)
        settings, _ = store.get()
        store.update(settings, 0, set())
        settings["location"]["name"] = "Anders"
        with self.assertRaises(ConflictError):
            store.update(settings, 0, set())
        self.assertEqual(store.get()[0]["location"]["name"], "Kassel")

    def test_invalid_update_leaves_file_and_memory_alone(self):
        store = SettingsStore(self.path, CATALOG, DEFAULTS)
        settings, _ = store.get()
        settings["widgets"][0]["x"] = 99
        with self.assertRaises(SettingsError):
            store.update(settings, 0, set())
        self.assertFalse(self.path.exists())
        self.assertEqual(store.get()[0]["widgets"][0]["x"], 0)

    def test_broken_file_falls_back_to_defaults(self):
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertLogs("kiosk", "ERROR"):
            store = SettingsStore(self.path, CATALOG, DEFAULTS)
        self.assertEqual(store.get()[0], DEFAULTS)

        self.path.write_text(json.dumps({**DEFAULTS, "widgets": [{"id": "x"}]}), encoding="utf-8")
        with self.assertLogs("kiosk", "ERROR"):
            SettingsStore(self.path, CATALOG, DEFAULTS)


if __name__ == "__main__":
    unittest.main()
