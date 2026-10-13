"""The one HTTP client of the server. Every outbound request goes through fetch(), so timeouts,
size limits, proxy handling (urllib reads HTTPS_PROXY) and the user agent live in one place."""

import json
import urllib.error
import urllib.request

USER_AGENT = "kiosk/1.0 (+https://github.com/mauricekleindienst/kiosk)"
TIMEOUT_SECONDS = 15
# Feeds and forecasts are a few hundred KB; anything far larger is not what we asked for.
MAX_BYTES = 4 * 1024 * 1024


class FetchError(Exception):
    pass


def fetch(url, accept="*/*"):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as err:
        raise FetchError(f"{url} answered HTTP {err.code}") from err
    except (urllib.error.URLError, OSError) as err:
        reason = getattr(err, "reason", err)
        raise FetchError(f"{url} is not reachable: {reason}") from err
    if len(body) > MAX_BYTES:
        raise FetchError(f"{url} sent more than {MAX_BYTES} bytes")
    return body


def fetch_json(url):
    body = fetch(url, accept="application/json")
    try:
        return json.loads(body)
    except ValueError as err:
        raise FetchError(f"{url} did not send valid JSON: {err}") from err
