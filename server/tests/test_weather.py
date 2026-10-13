import unittest
from datetime import date, datetime, timedelta, timezone

from kiosk.weather import build_weather, daily_icon, request_urls, sun_times

from helpers import BERLIN, berlin, fixture_json, forecast

KASSEL = (51.3127, 9.4797)


def build(forecast_raw, now, current=None, alerts=None):
    return build_weather(
        current if current is not None else fixture_json("brightsky-current.json"),
        forecast_raw,
        alerts if alerts is not None else fixture_json("brightsky-alerts.json"),
        now, "Kassel", *KASSEL, BERLIN,
    )


class BuildWeatherTest(unittest.TestCase):
    def setUp(self):
        self.now = berlin(2026, 10, 13, 9, 41)
        self.raw = forecast(berlin(2026, 10, 13, 0), 24 * 8 + 6)

    def test_current_conditions(self):
        current = build(self.raw, self.now)["current"]
        self.assertEqual(current["temperature"], 10.4)
        self.assertEqual(current["icon"], "partly-cloudy-day")
        self.assertEqual(current["windSpeed"], 13.7)
        self.assertEqual(current["windGust"], 27.4)
        self.assertEqual(current["humidity"], 78)

    def test_hourly_starts_at_the_current_hour(self):
        hourly = build(self.raw, self.now)["hourly"]
        self.assertEqual(len(hourly), 12)
        self.assertEqual(hourly[0]["time"], "2026-10-13T09:00:00+02:00")
        self.assertEqual(hourly[-1]["time"], "2026-10-13T20:00:00+02:00")

    def test_daily_has_seven_full_days_with_min_and_max(self):
        daily = build(self.raw, self.now)["daily"]
        self.assertEqual([d["date"] for d in daily][0], "2026-10-13")
        self.assertEqual(len(daily), 7)
        self.assertEqual(daily[0]["min"], 5.0)
        self.assertEqual(daily[0]["max"], 16.5)

    def test_partial_last_day_is_dropped(self):
        raw = forecast(berlin(2026, 10, 13, 0), 24 * 3 + 10)
        self.assertEqual([d["date"] for d in build(raw, self.now)["daily"]], ["2026-10-13", "2026-10-14", "2026-10-15"])

    def test_days_follow_berlin_dates_across_the_dst_change(self):
        # 25 October 2026: clocks go back, the day has 25 hours.
        raw = forecast(berlin(2026, 10, 24, 0), 24 * 4)
        weather = build(raw, berlin(2026, 10, 24, 12))
        dates = [d["date"] for d in weather["daily"]]
        self.assertEqual(dates[:3], ["2026-10-24", "2026-10-25", "2026-10-26"])

    def test_expired_alerts_are_dropped_and_the_most_severe_comes_first(self):
        alerts = build(self.raw, self.now)["alerts"]
        self.assertEqual([a["event"] for a in alerts], ["STARKREGEN", "WINDBÖEN"])
        self.assertEqual(alerts[0]["headline"], "Amtliche UNWETTERWARNUNG vor STARKREGEN")

    def test_missing_current_and_alerts_degrade_instead_of_failing(self):
        weather = build_weather({}, self.raw, None, self.now, "Kassel", *KASSEL, BERLIN)
        self.assertIsNone(weather["current"])
        self.assertEqual(weather["alerts"], [])
        self.assertEqual(len(weather["daily"]), 7)

    def test_empty_forecast_is_an_error(self):
        with self.assertRaises(ValueError):
            build({"weather": []}, self.now)

    def test_unknown_icon_falls_back_to_cloudy(self):
        raw = forecast(berlin(2026, 10, 13, 0), 30, icon_at=lambda m: None)
        self.assertEqual(build(raw, self.now)["hourly"][0]["icon"], "cloudy")

    def test_request_urls(self):
        urls = request_urls("https://api.brightsky.dev", *KASSEL, "Europe/Berlin", date(2026, 10, 13))
        self.assertEqual(
            urls["forecast"],
            "https://api.brightsky.dev/weather?lat=51.3127&lon=9.4797&tz=Europe%2FBerlin&date=2026-10-13&last_date=2026-10-21",
        )
        self.assertTrue(urls["current"].startswith("https://api.brightsky.dev/current_weather?lat=51.3127"))


class DailyIconTest(unittest.TestCase):
    def test_one_wet_hour_does_not_make_a_rainy_day(self):
        self.assertEqual(daily_icon(["clear-day"] * 10 + ["rain"]), "clear-day")

    def test_three_wet_hours_do(self):
        self.assertEqual(daily_icon(["clear-day"] * 8 + ["rain"] * 3), "rain")

    def test_snow_wins_over_rain(self):
        self.assertEqual(daily_icon(["rain"] * 4 + ["snow"] * 3), "snow")

    def test_a_single_thunderstorm_hour_counts(self):
        self.assertEqual(daily_icon(["clear-day"] * 12 + ["thunderstorm"]), "thunderstorm")

    def test_night_variants_map_to_day_and_ties_prefer_clouds(self):
        self.assertEqual(daily_icon(["clear-night", "cloudy"]), "cloudy")
        self.assertEqual(daily_icon(["partly-cloudy-night"] * 3), "partly-cloudy-day")

    def test_empty(self):
        self.assertEqual(daily_icon([]), "cloudy")


class SunTimesTest(unittest.TestCase):
    def local(self, moment):
        return moment.astimezone(BERLIN)

    def assertBetween(self, moment, earliest, latest):
        clock = self.local(moment).strftime("%H:%M")
        self.assertTrue(earliest <= clock <= latest, f"{clock} not within {earliest}-{latest}")

    def test_kassel_midsummer(self):
        sunrise, sunset = sun_times(date(2026, 6, 21), *KASSEL)
        self.assertBetween(sunrise, "04:55", "05:10")
        self.assertBetween(sunset, "21:35", "21:50")
        self.assertAlmostEqual((sunset - sunrise) / timedelta(hours=1), 16.6, delta=0.25)

    def test_kassel_midwinter(self):
        sunrise, sunset = sun_times(date(2026, 12, 21), *KASSEL)
        self.assertBetween(sunrise, "08:10", "08:30")
        self.assertBetween(sunset, "16:05", "16:25")

    def test_equinox_noon_follows_longitude(self):
        sunrise, sunset = sun_times(date(2026, 3, 20), *KASSEL)
        noon = sunrise + (sunset - sunrise) / 2
        # 12:00 UTC minus 9.48 degrees * 4 min, plus about 7 min equation of time: about 11:29 UTC.
        expected = datetime(2026, 3, 20, 11, 29, tzinfo=timezone.utc)
        self.assertLess(abs(noon - expected), timedelta(minutes=4))

    def test_polar_night_and_day_have_no_sunrise(self):
        self.assertEqual(sun_times(date(2026, 12, 21), 78.2, 15.6), (None, None))
        self.assertEqual(sun_times(date(2026, 6, 21), 78.2, 15.6), (None, None))


if __name__ == "__main__":
    unittest.main()
