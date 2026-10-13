"""When the screen sleeps. The screen has the same rule in web/shared/js/schedule.js; both are
tested against the same cases (tests/unit/schedule.test.js and server/tests/test_schedule.py)."""


def _minutes(text):
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


def is_sleeping(sleep, local_now):
    """`sleep` is display.sleep from the settings, `local_now` a datetime in the office time zone."""
    if not sleep.get("enabled"):
        return False
    if sleep.get("weekends") and local_now.weekday() >= 5:
        return True
    now = local_now.hour * 60 + local_now.minute
    start, end = _minutes(sleep["from"]), _minutes(sleep["to"])
    if start == end:
        return False
    # A window like 19:00-07:00 crosses midnight.
    return start <= now < end if start < end else now >= start or now < end
