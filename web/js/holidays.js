// Public holidays in Hesse (Hessisches Feiertagsgesetz): the nine national ones plus Fronleichnam.

import { daysBetween } from "./format.js";

/** Easter Sunday (Gregorian calendar, anonymous algorithm by Meeus/Jones/Butcher) as "YYYY-MM-DD". */
export function easterSunday(year) {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function addDays(isoDay, days) {
  const date = new Date(`${isoDay}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function hesseHolidays(year) {
  const easter = easterSunday(year);
  const holidays = [
    [`${year}-01-01`, "Neujahr"],
    [addDays(easter, -2), "Karfreitag"],
    [addDays(easter, 1), "Ostermontag"],
    [`${year}-05-01`, "Tag der Arbeit"],
    [addDays(easter, 39), "Christi Himmelfahrt"],
    [addDays(easter, 50), "Pfingstmontag"],
    [addDays(easter, 60), "Fronleichnam"],
    [`${year}-10-03`, "Tag der Deutschen Einheit"],
    [`${year}-12-25`, "1. Weihnachtstag"],
    [`${year}-12-26`, "2. Weihnachtstag"],
  ];
  return holidays.map(([date, name]) => ({ date, name })).sort((x, y) => x.date.localeCompare(y.date));
}

/** The holiday on or after `today` ("YYYY-MM-DD"), with the number of days until it. */
export function nextHoliday(today) {
  const year = Number(today.slice(0, 4));
  const upcoming = [...hesseHolidays(year), ...hesseHolidays(year + 1)].find((holiday) => holiday.date >= today);
  return { ...upcoming, daysUntil: daysBetween(today, upcoming.date) };
}
