// Geometry of the tile grid, shared by the admin editor and its tests. Widgets are rectangles
// {x, y, w, h} in grid cells; the server checks the same rules (settings.py).

export function overlaps(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

export function insideGrid(rect, grid) {
  return rect.x >= 0 && rect.y >= 0 && rect.x + rect.w <= grid.columns && rect.y + rect.h <= grid.rows;
}

/** Whether `rect` may take the place of the widget `id` (null for a new one). */
export function canPlace(widgets, id, rect, grid, minSize = { w: 1, h: 1 }) {
  if (rect.w < minSize.w || rect.h < minSize.h || !insideGrid(rect, grid)) return false;
  return widgets.every((other) => other.id === id || !overlaps(rect, other));
}

/** The first free spot for a w x h rectangle, scanning rows top to bottom; null if none. */
export function findFreeSpot(widgets, size, grid) {
  for (let y = 0; y + size.h <= grid.rows; y += 1) {
    for (let x = 0; x + size.w <= grid.columns; x += 1) {
      const rect = { x, y, w: size.w, h: size.h };
      if (canPlace(widgets, null, rect, grid)) return rect;
    }
  }
  return null;
}

/** A spot for a new widget: its preferred size if possible, else smaller down to its minimum. */
export function placeNew(widgets, kind, grid) {
  for (let h = kind.size.h; h >= kind.minSize.h; h -= 1) {
    for (let w = kind.size.w; w >= kind.minSize.w; w -= 1) {
      const spot = findFreeSpot(widgets, { w, h }, grid);
      if (spot) return spot;
    }
  }
  return null;
}

/** The widgets with one of them moved to `rect`, or null if it does not fit there. */
export function withRect(widgets, id, rect, grid, minSize) {
  if (!canPlace(widgets, id, rect, grid, minSize)) return null;
  return widgets.map((widget) => (widget.id === id ? { ...widget, ...rect } : widget));
}

/** Cells of the grid that no widget covers, as rectangles of one cell (for the editor). */
export function freeCells(widgets, grid) {
  const cells = [];
  for (let y = 0; y < grid.rows; y += 1) {
    for (let x = 0; x < grid.columns; x += 1) {
      const cell = { x, y, w: 1, h: 1 };
      if (!widgets.some((widget) => overlaps(cell, widget))) cells.push(cell);
    }
  }
  return cells;
}

/** A widget id that is not taken yet, derived from the type ("news", "news-2", ...). */
export function newWidgetId(widgets, type) {
  const taken = new Set(widgets.map((widget) => widget.id));
  if (!taken.has(type)) return type;
  for (let n = 2; ; n += 1) if (!taken.has(`${type}-${n}`)) return `${type}-${n}`;
}

/** Converts a pointer position inside the grid element into a cell, clamped to the grid. */
export function cellAt(point, box, grid) {
  const x = Math.floor(((point.x - box.left) / box.width) * grid.columns);
  const y = Math.floor(((point.y - box.top) / box.height) * grid.rows);
  return { x: Math.min(Math.max(x, 0), grid.columns - 1), y: Math.min(Math.max(y, 0), grid.rows - 1) };
}
