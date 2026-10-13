// When the screen sleeps. The server has the same rule in server/kiosk/schedule.py; both are tested
// against the same cases.

const minutesOf = (text) => {
  const [hours, minutes] = text.split(":").map(Number);
  return hours * 60 + minutes;
};

/** `sleep` is display.sleep; `parts` the local time as from zonedParts (year, month, day, hour, minute). */
export function isSleeping(sleep, parts) {
  if (!sleep?.enabled) return false;
  const weekday = new Date(Date.UTC(parts.year, parts.month - 1, parts.day)).getUTCDay();
  if (sleep.weekends && (weekday === 0 || weekday === 6)) return true;
  const now = parts.hour * 60 + parts.minute;
  const start = minutesOf(sleep.from);
  const end = minutesOf(sleep.to);
  if (start === end) return false;
  // A window like 19:00-07:00 crosses midnight.
  return start < end ? now >= start && now < end : now >= start || now < end;
}
