import assert from "node:assert/strict";
import { test } from "node:test";

import { easterSunday, hesseHolidays, nextHoliday } from "../../web/js/holidays.js";

test("Easter Sunday", () => {
  assert.equal(easterSunday(2024), "2024-03-31");
  assert.equal(easterSunday(2025), "2025-04-20");
  assert.equal(easterSunday(2026), "2026-04-05");
  assert.equal(easterSunday(2027), "2027-03-28");
  assert.equal(easterSunday(2038), "2038-04-25");
});

test("the ten public holidays of Hesse in 2026", () => {
  assert.deepEqual(hesseHolidays(2026).map((holiday) => `${holiday.date} ${holiday.name}`), [
    "2026-01-01 Neujahr",
    "2026-04-03 Karfreitag",
    "2026-04-06 Ostermontag",
    "2026-05-01 Tag der Arbeit",
    "2026-05-14 Christi Himmelfahrt",
    "2026-05-25 Pfingstmontag",
    "2026-06-04 Fronleichnam",
    "2026-10-03 Tag der Deutschen Einheit",
    "2026-12-25 1. Weihnachtstag",
    "2026-12-26 2. Weihnachtstag",
  ]);
});

test("next holiday, today and across the new year", () => {
  assert.deepEqual(nextHoliday("2026-10-13"), { date: "2026-12-25", name: "1. Weihnachtstag", daysUntil: 73 });
  assert.equal(nextHoliday("2026-10-03").daysUntil, 0);
  assert.deepEqual(nextHoliday("2026-12-27"), { date: "2027-01-01", name: "Neujahr", daysUntil: 5 });
  assert.equal(nextHoliday("2026-03-28").name, "Karfreitag", "counts dates across the DST change");
  assert.equal(nextHoliday("2026-03-28").daysUntil, 6);
});
