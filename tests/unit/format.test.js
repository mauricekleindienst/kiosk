import assert from "node:assert/strict";
import { test } from "node:test";

import {
  daysBetween, formatAge, formatClock, formatLongDate, formatMillimetres, formatPercent, formatSpeed,
  formatTemperature, isoDay, isoWeek, weekdayShort, zonedParts,
} from "../../web/js/format.js";

const BERLIN = "Europe/Berlin";

test("clock and date follow the office time zone, not the machine's", () => {
  const instant = new Date("2026-10-13T07:05:00Z");
  assert.equal(formatClock(instant, BERLIN), "09:05");
  assert.equal(formatClock(instant, "UTC"), "07:05");
  assert.equal(formatLongDate(instant, BERLIN), "Dienstag, 13. Oktober 2026");
});

test("the day changes at Berlin midnight", () => {
  const instant = new Date("2026-12-01T23:30:00Z");
  assert.equal(isoDay(instant, BERLIN), "2026-12-02");
  assert.equal(formatClock(instant, BERLIN), "00:30");
  assert.deepEqual(zonedParts(instant, BERLIN), { year: 2026, month: 12, day: 2, hour: 0, minute: 30, second: 0 });
});

test("midnight shows as 00, not 24", () => {
  assert.equal(formatClock(new Date("2026-06-30T22:00:00Z"), BERLIN), "00:00");
});

test("ISO week numbers, including the year boundaries", () => {
  assert.equal(isoWeek("2026-10-13"), 42);
  assert.equal(isoWeek("2026-01-01"), 1, "a Thursday starts week 1");
  assert.equal(isoWeek("2027-01-01"), 53, "a Friday still belongs to the last week of 2026");
  assert.equal(isoWeek("2021-01-03"), 53);
  assert.equal(isoWeek("2024-12-30"), 1);
  assert.equal(isoWeek("2024-02-29"), 9);
});

test("days between calendar days ignore the DST change", () => {
  assert.equal(daysBetween("2026-03-28", "2026-03-30"), 2);
  assert.equal(daysBetween("2026-10-24", "2026-10-26"), 2);
  assert.equal(daysBetween("2026-12-31", "2027-01-01"), 1);
  assert.equal(daysBetween("2026-10-13", "2026-10-13"), 0);
});

test("short weekday names", () => {
  assert.deepEqual(["2026-10-12", "2026-10-13", "2026-10-18"].map(weekdayShort), ["Mo", "Di", "So"]);
});

test("temperatures use a real minus sign and never show minus zero", () => {
  assert.equal(formatTemperature(14.5), "15°");
  assert.equal(formatTemperature(-0.4), "0°");
  assert.equal(formatTemperature(-3.6), "−4°");
  assert.equal(formatTemperature(0), "0°");
  assert.equal(formatTemperature(null), "–");
  assert.equal(formatTemperature(undefined), "–");
});

test("units use a narrow no-break space and the decimal comma", () => {
  assert.equal(formatPercent(30), "30 %");
  assert.equal(formatSpeed(13.7), "14 km/h");
  assert.equal(formatMillimetres(1.25), "1,3 mm");
  assert.equal(formatMillimetres(12), "12 mm");
});

test("ages of headlines", () => {
  const now = Date.parse("2026-10-13T10:00:00Z");
  const ago = (minutes) => formatAge(now - minutes * 60000, now);
  assert.equal(ago(0.5), "gerade eben");
  assert.equal(ago(-5), "gerade eben", "a timestamp from the future (clock skew) is not negative");
  assert.equal(ago(1), "vor 1 Min.");
  assert.equal(ago(59), "vor 59 Min.");
  assert.equal(ago(60), "vor 1 Std.");
  assert.equal(ago(23 * 60 + 59), "vor 23 Std.");
  assert.equal(ago(24 * 60), "vor 1 Tag");
  assert.equal(ago(3 * 24 * 60), "vor 3 Tagen");
});
