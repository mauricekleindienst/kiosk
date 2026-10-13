"""Share prices for the stock widget from Yahoo Finance's chart endpoint (no key, delayed by about
15 minutes on Xetra, unofficial: it may change or refuse requests without notice). The rest of the
server only sees the model built here, so another provider can replace it."""

from datetime import datetime, timezone
from urllib.parse import quote, urlencode

# Five-minute points cover a trading day in about 100 points: smooth enough for a small chart.
INTERVAL = "5m"


def request_url(base_url, symbol):
    return f"{base_url}/v8/finance/chart/{quote(symbol, safe='')}?{urlencode({'range': '1d', 'interval': INTERVAL})}"


def _iso(seconds):
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat() if seconds else None


def build_quote(raw):
    """The price, the change against yesterday's close and the day's curve."""
    chart = (raw or {}).get("chart") or {}
    if chart.get("error"):
        error = chart["error"]
        raise ValueError(f"stock provider refused: {error.get('description') or error.get('code') or error}")
    results = chart.get("result") or []
    if not results:
        raise ValueError("stock provider sent no result")
    result = results[0]
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    previous = meta.get("chartPreviousClose") if meta.get("chartPreviousClose") is not None else meta.get("previousClose")
    if price is None:
        raise ValueError("stock provider sent no price")
    closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    points = [[_iso(moment), round(float(close), 4)]
              for moment, close in zip(result.get("timestamp") or [], closes) if close is not None]
    change = None if previous in (None, 0) else price - previous
    session = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    return {
        "symbol": meta.get("symbol"),
        "name": meta.get("longName") or meta.get("shortName") or meta.get("symbol"),
        "currency": meta.get("currency"),
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
        "price": float(price),
        "previousClose": None if previous is None else float(previous),
        "change": None if change is None else round(change, 4),
        "changePercent": None if change is None else round(change / previous * 100, 4),
        "time": _iso(meta.get("regularMarketTime")),
        "sessionStart": _iso(session.get("start")),
        "sessionEnd": _iso(session.get("end")),
        "points": points,
    }
