import unittest
from datetime import datetime, timezone

from kiosk.feeds import FeedError, Headline, parse_feed, select_headlines

from helpers import fixture_bytes

NOW = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)


class ParseFeedTest(unittest.TestCase):
    def test_google_news_titles_lose_the_outlet_suffix_and_keep_umlauts(self):
        headlines = parse_feed(fixture_bytes("google-news-rheinmetall.xml"))
        self.assertEqual(headlines[0].title, "Rheinmetall erhält Großauftrag für Munition")
        self.assertEqual(headlines[0].source, "Handelsblatt")
        self.assertEqual(headlines[0].published, datetime(2026, 10, 13, 5, 10, tzinfo=timezone.utc))

    def test_double_escaped_entities_are_decoded(self):
        headlines = parse_feed(fixture_bytes("google-news-rheinmetall.xml"))
        self.assertEqual(headlines[1].title, "Aktie im Fokus: Rheinmetall & Co. legen zu")

    def test_items_without_a_title_are_skipped(self):
        titles = [h.title for h in parse_feed(fixture_bytes("google-news-rheinmetall.xml"))]
        self.assertEqual(len(titles), 5)
        self.assertNotIn("", titles)

    def test_atom_feed_strips_html_and_falls_back_to_updated(self):
        headlines = parse_feed(fixture_bytes("atom.xml"))
        self.assertEqual(headlines[0].title, "Halbjahreszahlen veröffentlicht")
        self.assertEqual(headlines[0].source, "Pressemitteilungen")
        self.assertEqual(headlines[1].published, datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc))

    def test_title_that_is_only_the_outlet_name_is_kept(self):
        body = b"<rss><channel><title>X</title><item><title>ab - ab</title><source>ab - ab</source></item></channel></rss>"
        self.assertEqual(parse_feed(body)[0].title, "ab - ab")

    def test_broken_xml_and_unknown_formats_raise_feed_error(self):
        with self.assertRaises(FeedError):
            parse_feed(b"<rss><channel>")
        with self.assertRaises(FeedError):
            parse_feed(b"<html><body>Consent required</body></html>")
        with self.assertRaises(FeedError):
            parse_feed(b"<rss></rss>")

    def test_unparseable_dates_become_none(self):
        body = b"<rss><channel><title>X</title><item><title>A</title><pubDate>gestern</pubDate></item></channel></rss>"
        self.assertIsNone(parse_feed(body)[0].published)


class SelectHeadlinesTest(unittest.TestCase):
    def test_newest_first_without_duplicates_or_old_items(self):
        picked = select_headlines(parse_feed(fixture_bytes("google-news-rheinmetall.xml")), NOW, 10, 7)
        self.assertEqual(
            [h.source for h in picked],
            ["Handelsblatt", "boerse.de", "NDR"],
            "the FAZ duplicate (same title) and the item from 2025 must be dropped",
        )

    def test_limit(self):
        picked = select_headlines(parse_feed(fixture_bytes("google-news-rheinmetall.xml")), NOW, 2, 7)
        self.assertEqual(len(picked), 2)

    def test_undated_items_come_last_and_future_items_count_as_now(self):
        future = Headline("Zukunft", "A", datetime(2026, 10, 14, tzinfo=timezone.utc))
        undated = Headline("Ohne Datum", "B", None)
        recent = Headline("Neu", "C", datetime(2026, 10, 13, 6, 59, tzinfo=timezone.utc))
        picked = select_headlines([undated, recent, future], NOW, 10, 7)
        self.assertEqual([h.title for h in picked], ["Zukunft", "Neu", "Ohne Datum"])

    def test_empty_feed(self):
        self.assertEqual(select_headlines([], NOW, 5, 7), [])


if __name__ == "__main__":
    unittest.main()
