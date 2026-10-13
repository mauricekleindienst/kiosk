import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  canPlace, cellAt, findFreeSpot, freeCells, newWidgetId, overlaps, placeNew, withRect,
} from "../../web/shared/js/layout.js";

const catalog = JSON.parse(readFileSync(new URL("../../web/shared/widgets.json", import.meta.url), "utf8"));
const GRID = catalog.grid;
const DEFAULT = [
  { id: "clock", x: 0, y: 0, w: 7, h: 2 },
  { id: "news-main", x: 0, y: 2, w: 7, h: 4 },
  { id: "news-side", x: 0, y: 6, w: 7, h: 2 },
  { id: "weather", x: 7, y: 0, w: 5, h: 8 },
];

test("overlap is strict: touching edges do not overlap", () => {
  assert.equal(overlaps({ x: 0, y: 0, w: 2, h: 2 }, { x: 2, y: 0, w: 2, h: 2 }), false);
  assert.equal(overlaps({ x: 0, y: 0, w: 2, h: 2 }, { x: 1, y: 1, w: 2, h: 2 }), true);
});

test("placement respects the grid, other widgets and the minimum size", () => {
  assert.equal(canPlace(DEFAULT, "weather", { x: 7, y: 0, w: 5, h: 8 }, GRID), true, "a widget may stay where it is");
  assert.equal(canPlace(DEFAULT, "weather", { x: 6, y: 0, w: 5, h: 8 }, GRID), false);
  assert.equal(canPlace(DEFAULT, "weather", { x: 8, y: 0, w: 5, h: 8 }, GRID), false, "beyond the right edge");
  assert.equal(canPlace([], null, { x: 0, y: 0, w: 2, h: 2 }, GRID, { w: 3, h: 3 }), false);
});

test("a full screen has no free spot; a smaller weather column makes room", () => {
  assert.equal(findFreeSpot(DEFAULT, { w: 1, h: 1 }, GRID), null);
  const shorter = withRect(DEFAULT, "weather", { x: 7, y: 0, w: 5, h: 6 }, GRID);
  assert.deepEqual(findFreeSpot(shorter, { w: 5, h: 2 }, GRID), { x: 7, y: 6, w: 5, h: 2 });
  assert.equal(withRect(DEFAULT, "weather", { x: 7, y: 0, w: 5, h: 9 }, GRID), null);
});

test("new widgets shrink towards their minimum to fit", () => {
  const shorter = withRect(DEFAULT, "weather", { x: 7, y: 0, w: 5, h: 7 }, GRID);
  assert.deepEqual(placeNew(shorter, catalog.types.message, GRID), { x: 7, y: 7, w: 5, h: 1 });
  assert.equal(placeNew(shorter, catalog.types.calendar, GRID), null, "a calendar needs 3 x 3");
});

test("free cells and new ids", () => {
  assert.equal(freeCells(DEFAULT, GRID).length, 0);
  assert.equal(freeCells([], GRID).length, GRID.columns * GRID.rows);
  assert.equal(newWidgetId(DEFAULT, "message"), "message");
  assert.equal(newWidgetId([...DEFAULT, { id: "news" }, { id: "news-2" }], "news"), "news-3");
});

test("pointer positions map to cells and clamp at the edges", () => {
  const box = { left: 100, top: 50, width: 1200, height: 800 };
  assert.deepEqual(cellAt({ x: 100, y: 50 }, box, GRID), { x: 0, y: 0 });
  assert.deepEqual(cellAt({ x: 1299, y: 849 }, box, GRID), { x: 11, y: 7 });
  assert.deepEqual(cellAt({ x: 5000, y: -20 }, box, GRID), { x: 11, y: 0 });
});

test("every widget type in the catalog has sizes that fit the grid and a minimum below its default", () => {
  for (const [type, kind] of Object.entries(catalog.types)) {
    assert.ok(kind.size.w <= GRID.columns && kind.size.h <= GRID.rows, type);
    assert.ok(kind.minSize.w <= kind.size.w && kind.minSize.h <= kind.size.h, type);
    assert.ok(kind.label && kind.description, type);
    for (const option of kind.options) {
      assert.ok(option.key && option.label && option.type, `${type}.${option.key}`);
      if (option.type === "select") assert.ok(option.choices.some((choice) => choice.value === option.default), `${type}.${option.key}`);
      if (option.type === "number") assert.ok(option.min <= option.default && option.default <= option.max, `${type}.${option.key}`);
    }
  }
});
