// Date, time and number formatting for the screen. Everything takes the time zone explicitly, so
// the screen shows office time even when the Raspberry Pi itself runs on UTC.

const WEEKDAYS_SHORT = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
const MINUS = "−";
const NARROW_SPACE = " ";

const formatters = new Map();

function formatter(timeZone, options) {
  const key = timeZone + JSON.stringify(options);
  if (!formatters.has(key)) {
    formatters.set(key, new Intl.DateTimeFormat("de-DE", { timeZone, ...options }));
  }
  return formatters.get(key);
}

/** The calendar date and wall-clock time of `date` in `timeZone`, as numbers. */
export function zonedParts(date, timeZone) {
  const parts = {};
  const options = {
    year: "numeric", month: "numeric", day: "numeric",
    hour: "numeric", minute: "numeric", second: "numeric", hourCycle: "h23",
  };
  for (const part of formatter(timeZone, options).formatToParts(date)) {
    if (part.type !== "literal") parts[part.type] = Number(part.value);
  }
  return parts;
}

/** "2026-10-13" for the calendar day of `date` in `timeZone`. */
export function isoDay(date, timeZone) {
  const { year, month, day } = zonedParts(date, timeZone);
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** Whole days from one ISO calendar day to another (DST-safe: counts dates, not hours). */
export function daysBetween(fromIsoDay, toIsoDay) {
  return Math.round((Date.parse(`${toIsoDay}T00:00:00Z`) - Date.parse(`${fromIsoDay}T00:00:00Z`)) / 86400000);
}

export function formatClock(date, timeZone) {
  return formatter(timeZone, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
}

/** "Dienstag, 13. Oktober 2026" */
export function formatLongDate(date, timeZone) {
  return formatter(timeZone, { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(date);
}

/** ISO 8601 week number of a calendar day (weeks start on Monday; week 1 holds the first Thursday). */
export function isoWeek(isoDayString) {
  const day = new Date(`${isoDayString}T00:00:00Z`);
  const weekday = day.getUTCDay() || 7;
  day.setUTCDate(day.getUTCDate() + 4 - weekday);
  const yearStart = Date.UTC(day.getUTCFullYear(), 0, 1);
  return Math.ceil(((day - yearStart) / 86400000 + 1) / 7);
}

export function weekdayShort(isoDayString) {
  return WEEKDAYS_SHORT[new Date(`${isoDayString}T12:00:00Z`).getUTCDay()];
}

/** "14°", "−3°"; never "−0°". */
export function formatTemperature(value) {
  if (value == null || Number.isNaN(value)) return "–";
  const rounded = Math.round(value);
  return rounded < 0 ? `${MINUS}${-rounded}°` : `${rounded === 0 ? 0 : rounded}°`;
}

export function formatPercent(value) {
  return `${Math.round(value)}${NARROW_SPACE}%`;
}

export function formatSpeed(kmh) {
  return `${Math.round(kmh)}${NARROW_SPACE}km/h`;
}

/** "1,2 mm" with the German decimal comma. */
export function formatMillimetres(mm) {
  const number = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 }).format(mm);
  return `${number}${NARROW_SPACE}mm`;
}

/** "gerade eben", "vor 5 Min.", "vor 2 Std.", "vor 1 Tag", "vor 3 Tagen". */
export function formatAge(then, now) {
  const minutes = Math.floor((now - then) / 60000);
  if (minutes < 1) return "gerade eben";
  if (minutes < 60) return `vor ${minutes} Min.`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `vor ${hours} Std.`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "vor 1 Tag" : `vor ${days} Tagen`;
}
