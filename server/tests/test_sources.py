import json
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from kiosk import stock, transit
from kiosk.schedule import is_sleeping

from helpers import berlin, fixture_json

CASES = json.loads((Path(__file__).resolve().parents[2] / "tests" / "schedule-cases.json").read_text(encoding="utf-8"))


class ScheduleTest(unittest.TestCase):
    def test_shared_cases(self):
        for case in CASES:
            with self.subTest(case["why"]):
                local = datetime.fromisoformat(case["at"]).replace(tzinfo=ZoneInfo("Europe/Berlin"))
                self.assertEqual(is_sleeping(case["sleep"], local), case["sleeping"])


class StockTest(unittest.TestCase):
    def test_quote_change_and_curve(self):
        quote = stock.build_quote(fixture_json("yahoo-chart-rhm.json"))
        self.assertEqual((quote["symbol"], quote["name"], quote["currency"], quote["exchange"]), ("RHM.DE", "Rheinmetall AG", "EUR", "XETRA"))
        self.assertEqual(quote["price"], 1848.5)
        self.assertEqual(quote["previousClose"], 1830.0)
        self.assertEqual(quote["change"], 18.5)
        self.assertAlmostEqual(quote["changePercent"], 1.0109, places=3)
        self.assertEqual(len(quote["points"]), 19, "gaps in the curve are left out")
        self.assertEqual(quote["points"][0], ["2026-10-13T07:00:00+00:00", 1820.0])
        self.assertEqual(quote["sessionEnd"], "2026-10-13T15:30:00+00:00")

    def test_provider_errors_are_value_errors(self):
        with self.assertRaisesRegex(ValueError, "delisted"):
            stock.build_quote(fixture_json("yahoo-chart-error.json"))
        for raw in ({}, {"chart": {"result": []}}, {"chart": {"result": [{"meta": {}}]}}, None):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                stock.build_quote(raw)

    def test_without_previous_close_there_is_no_change(self):
        raw = fixture_json("yahoo-chart-rhm.json")
        meta = raw["chart"]["result"][0]["meta"]
        meta.pop("chartPreviousClose")
        meta.pop("previousClose")
        quote = stock.build_quote(raw)
        self.assertIsNone(quote["change"])
        self.assertIsNone(quote["changePercent"])

    def test_symbol_is_quoted_in_the_url(self):
        self.assertEqual(stock.request_url("https://q.example", "RHM.DE"), "https://q.example/v8/finance/chart/RHM.DE?range=1d&interval=5m")
        self.assertIn("%2F..%2F", stock.request_url("https://q.example", "/../x"))


class TransitTest(unittest.TestCase):
    def test_departures_soonest_first_with_delays_and_cancellations(self):
        departures = transit.build_departures(fixture_json("transit-departures.json"), berlin(2026, 10, 13, 9, 41))
        self.assertEqual([d["line"] for d in departures], ["Bus 16", "Tram 1", "RT 5", "RE 9", "Tram 4"],
                         "gone departures are dropped; a cancelled one stays at its planned time")
        tram = departures[1]
        self.assertEqual((tram["direction"], tram["delayMinutes"], tram["product"]), ("Wilhelmshöhe", 2, "tram"))
        self.assertEqual(tram["when"], "2026-10-13T09:48:00+02:00")
        cancelled = departures[2]
        self.assertTrue(cancelled["cancelled"])
        self.assertIsNone(cancelled["delayMinutes"])
        self.assertEqual(cancelled["platform"], "2")

    def test_garbage_is_a_value_error(self):
        with self.assertRaises(ValueError):
            transit.build_departures({"error": "x"}, berlin(2026, 10, 13, 9, 41))

    def test_stop_search_keeps_stops_with_ids(self):
        self.assertEqual(transit.build_stops(fixture_json("transit-locations.json")),
                         [{"id": "8000193", "name": "Kassel Hbf"}, {"id": "706070", "name": "Kassel Rathaus"}])
        self.assertEqual(transit.build_stops({"error": True}), [])

    def test_urls(self):
        url = transit.departures_url("https://t.example", "A=1@O=Kassel@", ["tram", "bus"])
        self.assertTrue(url.startswith("https://t.example/stops/A%3D1%40O%3DKassel%40/departures?duration=90"))
        self.assertIn("tram=true", url)
        self.assertIn("regional=false", url)
        self.assertIn("query=Kassel+Rathaus", transit.locations_url("https://t.example", "Kassel Rathaus"))


if __name__ == "__main__":
    unittest.main()
