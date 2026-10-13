"""Parses RSS 2.0 and Atom feeds into headlines and picks the ones worth showing."""

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

ATOM = "{http://www.w3.org/2005/Atom}"
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_NOT_WORD = re.compile(r"\W+")


class FeedError(Exception):
    pass


@dataclass(frozen=True)
class Headline:
    title: str
    source: str
    published: datetime | None

    def to_json(self):
        return {
            "title": self.title,
            "source": self.source,
            "published": self.published.isoformat() if self.published else None,
        }


def _clean(text):
    """Feed titles may carry HTML tags and double-escaped entities; the screen wants plain text."""
    text = html.unescape(_TAG.sub(" ", text or ""))
    return _SPACE.sub(" ", text).strip()


def _parse_date(text):
    if not text:
        return None
    text = text.strip()
    try:
        parsed = parsedate_to_datetime(text)  # RSS: RFC 822
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))  # Atom: RFC 3339
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _headline(title, source):
    title = _clean(title)
    source = _clean(source)
    # Google News appends the outlet to every title ("Headline - Outlet"); the screen shows it apart.
    suffix = f" - {source}"
    if source and title.endswith(suffix) and len(title) > len(suffix):
        title = title[: -len(suffix)].rstrip()
    return title, source


def parse_feed(body):
    """Returns the headlines of an RSS 2.0 or Atom document, in feed order."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as err:
        raise FeedError(f"feed is not valid XML: {err}") from err

    headlines = []
    if root.tag == "rss":
        channel = root.find("channel")
        if channel is None:
            raise FeedError("RSS feed has no channel")
        channel_title = channel.findtext("title", "")
        for item in channel.iter("item"):
            title, source = _headline(item.findtext("title", ""), item.findtext("source") or channel_title)
            if title:
                headlines.append(Headline(title, source, _parse_date(item.findtext("pubDate"))))
    elif root.tag == f"{ATOM}feed":
        feed_title = root.findtext(f"{ATOM}title", "")
        for entry in root.iter(f"{ATOM}entry"):
            source = entry.findtext(f"{ATOM}source/{ATOM}title") or feed_title
            title, source = _headline(entry.findtext(f"{ATOM}title", ""), source)
            published = entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated")
            if title:
                headlines.append(Headline(title, source, _parse_date(published)))
    else:
        raise FeedError(f"unknown feed format <{root.tag}>")
    return headlines


def _dedupe_key(title):
    return _NOT_WORD.sub(" ", title.casefold()).strip()


def select_headlines(headlines, now, limit, max_age_days):
    """Newest first, nothing older than `max_age_days`, the same story only once. Undated items
    are kept after the dated ones; items dated in the future (clock skew) count as now."""
    oldest = now - timedelta(days=max_age_days)
    seen = set()
    picked = []
    for headline in headlines:
        if headline.published is not None and headline.published < oldest:
            continue
        key = _dedupe_key(headline.title)
        if key in seen:
            continue
        seen.add(key)
        picked.append(headline)

    def sort_key(headline):
        if headline.published is None:
            return (1, 0.0)
        return (0, -min(headline.published, now).timestamp())

    picked.sort(key=sort_key)
    return picked[:limit]
