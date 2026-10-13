import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { isSleeping } from "../../web/shared/js/schedule.js";

// The same cases as server/tests/test_sources.py: screen and server must agree when the night starts.
const cases = JSON.parse(readFileSync(new URL("../schedule-cases.json", import.meta.url), "utf8"));

for (const testCase of cases) {
  test(`night schedule: ${testCase.why}`, () => {
    const [date, time] = testCase.at.split("T");
    const [year, month, day] = date.split("-").map(Number);
    const [hour, minute] = time.split(":").map(Number);
    assert.equal(isSleeping(testCase.sleep, { year, month, day, hour, minute }), testCase.sleeping);
  });
}
