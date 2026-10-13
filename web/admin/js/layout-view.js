// The layout editor: a grid of tiles to drag, resize and select, a settings panel for the
// selected tile, new tiles and templates. Every action also works with the keyboard.

import { canPlace, cellAt, newWidgetId, placeNew, withRect } from "../../shared/js/layout.js";
import { defaultOptions, widgetForm } from "./forms.js";
import { draft, save, store, widgetLabel } from "./store.js";
import { t } from "./strings.js";
import { applyTemplate, TEMPLATES } from "./templates.js";
import { button, confirmDialog, field, h, toast } from "./ui.js";

const FIELD_ERROR_PREFIX = /^widgets\.(\d+)\.(?:options\.)?([A-Za-z]+)/;

let mode = "grid";

function selectedWidget() {
  return store.settings.widgets.find((widget) => widget.id === store.selected) ?? null;
}

function aspectRatio(status) {
  const screen = status?.screen;
  return screen?.width && screen?.height ? `${screen.width} / ${screen.height}` : "16 / 9";
}

function saveWidgets(widgets, message) {
  const next = draft();
  next.widgets = widgets;
  return save(next, message);
}

function announce(text) {
  const region = document.getElementById("announce");
  if (region) region.textContent = text;
}

function moveOrResize(widget, rect, kind, rerender) {
  const minSize = store.catalog.types[widget.type].minSize;
  const widgets = withRect(store.settings.widgets, widget.id, rect, store.catalog.grid, minSize);
  if (!widgets) {
    announce(t.cannotMove);
    return false;
  }
  const label = widgetLabel(widget);
  const resized = rect.w !== widget.w || rect.h !== widget.h;
  saveWidgets(widgets, resized ? t.resized(label) : t.moved(label));
  announce(t.tileAnnounce(label, rect.x, rect.y, rect.w, rect.h));
  rerender();
  return true;
}

function gridEditor(rerender, status) {
  const grid = store.catalog.grid;
  const board = h("div", { class: "board", role: "listbox", "aria-label": t.layoutTitle });
  board.style.aspectRatio = aspectRatio(status);
  board.style.setProperty("--columns", grid.columns);
  board.style.setProperty("--rows", grid.rows);
  for (let y = 0; y < grid.rows; y += 1) {
    for (let x = 0; x < grid.columns; x += 1) {
      const cell = h("span", { class: "board-cell", "aria-hidden": "true" });
      cell.style.gridArea = `${y + 1} / ${x + 1}`;
      board.append(cell);
    }
  }

  for (const widget of store.settings.widgets) {
    const kind = store.catalog.types[widget.type];
    const selected = widget.id === store.selected;
    const tile = h("div", {
      class: selected ? "board-tile is-selected" : "board-tile",
      role: "option",
      tabindex: selected || (!store.selected && widget === store.settings.widgets[0]) ? "0" : "-1",
      "aria-selected": String(selected),
      "aria-label": t.tileAnnounce(widgetLabel(widget), widget.x, widget.y, widget.w, widget.h),
      "data-widget": widget.id,
    }, h("span", { class: "board-tile-type", text: kind.label }), h("span", { class: "board-tile-detail", text: widget.options.title ?? widget.options.label ?? "" }),
    h("span", { class: "board-tile-size", text: t.cells(widget.w, widget.h) }));
    const place = (rect) => {
      tile.style.gridColumn = `${rect.x + 1} / span ${rect.w}`;
      tile.style.gridRow = `${rect.y + 1} / span ${rect.h}`;
    };
    place(widget);
    const handle = h("span", { class: "board-handle", "aria-hidden": "true" });
    tile.append(handle);

    tile.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const resizing = event.target === handle;
      const box = board.getBoundingClientRect();
      const start = cellAt({ x: event.clientX, y: event.clientY }, box, grid);
      const offset = { x: start.x - widget.x, y: start.y - widget.y };
      let candidate = { x: widget.x, y: widget.y, w: widget.w, h: widget.h };
      let moved = false;
      tile.setPointerCapture(event.pointerId);
      tile.classList.add("is-dragging");
      const onMove = (moveEvent) => {
        const cell = cellAt({ x: moveEvent.clientX, y: moveEvent.clientY }, box, grid);
        const next = resizing
          ? { x: widget.x, y: widget.y, w: Math.max(1, cell.x - widget.x + 1), h: Math.max(1, cell.y - widget.y + 1) }
          : { x: Math.min(Math.max(cell.x - offset.x, 0), grid.columns - widget.w), y: Math.min(Math.max(cell.y - offset.y, 0), grid.rows - widget.h), w: widget.w, h: widget.h };
        if (next.x === candidate.x && next.y === candidate.y && next.w === candidate.w && next.h === candidate.h) return;
        moved = true;
        candidate = next;
        place(candidate);
        tile.classList.toggle("is-blocked", !canPlace(store.settings.widgets, widget.id, candidate, grid, kind.minSize));
      };
      const onUp = () => {
        tile.removeEventListener("pointermove", onMove);
        tile.removeEventListener("pointerup", onUp);
        tile.removeEventListener("pointercancel", onUp);
        tile.classList.remove("is-dragging", "is-blocked");
        store.selected = widget.id;
        const changed = candidate.x !== widget.x || candidate.y !== widget.y || candidate.w !== widget.w || candidate.h !== widget.h;
        if (!moved || !changed || !moveOrResize(widget, candidate, kind, rerender)) {
          place(widget);
          rerender();
        }
      };
      tile.addEventListener("pointermove", onMove);
      tile.addEventListener("pointerup", onUp);
      tile.addEventListener("pointercancel", onUp);
    });

    tile.addEventListener("keydown", async (event) => {
      const steps = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
      if (steps[event.key]) {
        event.preventDefault();
        const [dx, dy] = steps[event.key];
        const rect = event.shiftKey
          ? { x: widget.x, y: widget.y, w: widget.w + dx, h: widget.h + dy }
          : { x: widget.x + dx, y: widget.y + dy, w: widget.w, h: widget.h };
        store.selected = widget.id;
        if (!moveOrResize(widget, rect, kind, rerender)) rerender();
      } else if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        await removeWidget(widget, rerender);
      } else if (event.key === "Escape") {
        store.selected = null;
        rerender();
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        store.selected = widget.id;
        rerender();
        document.querySelector(".inspector input, .inspector select, .inspector textarea")?.focus();
      }
    });
    tile.addEventListener("focus", () => {
      if (store.selected !== widget.id) {
        store.selected = widget.id;
        rerender();
      }
    });
    board.append(tile);
  }
  return board;
}

function preview(status) {
  const frame = h("iframe", { class: "preview-frame", src: "/screen/", title: t.viewPreview, tabindex: "-1" });
  const width = status?.screen?.width || 1920;
  const height = status?.screen?.height || 1080;
  const box = h("div", { class: "preview" }, frame);
  box.style.aspectRatio = `${width} / ${height}`;
  frame.style.width = `${width}px`;
  frame.style.height = `${height}px`;
  // Render at the real size and scale down, so the preview shows exactly what the screen shows.
  new ResizeObserver(([entry]) => {
    frame.style.transform = `scale(${entry.contentRect.width / width})`;
  }).observe(box);
  return h("div", {}, box, h("p", { class: "field-hint", text: t.previewHint }));
}

async function removeWidget(widget, rerender) {
  const label = widgetLabel(widget);
  if (!(await confirmDialog(t.removeConfirm(label), t.remove))) return;
  store.selected = null;
  await saveWidgets(store.settings.widgets.filter((item) => item.id !== widget.id), t.removed(label));
  rerender();
  document.querySelector(".board-tile")?.focus();
}

function errorsFor(widget) {
  const error = store.lastError;
  const match = error?.path?.match(FIELD_ERROR_PREFIX);
  if (!match || store.settings.widgets[Number(match[1])]?.id !== widget.id) return {};
  return { [match[2]]: error.message };
}

function inspector(rerender) {
  const widget = selectedWidget();
  const panel = h("section", { class: "inspector card", "aria-label": widget ? widgetLabel(widget) : t.addTitle });
  if (!widget) {
    panel.append(h("p", { class: "muted", text: t.noSelection }));
    return panel;
  }
  const kind = store.catalog.types[widget.type];
  panel.append(
    h("div", { class: "inspector-head" },
      h("h2", { class: "card-title", text: widgetLabel(widget) }),
      button(t.done, () => {
        const id = store.selected;
        store.selected = null;
        rerender();
        document.querySelector(`.board-tile[data-widget="${id}"]`)?.focus();
      }, { variant: "link" })),
    h("p", { class: "muted", text: kind.description }),
  );

  const label = widgetLabel(widget);
  panel.append(widgetForm(kind, widget, {
    uploads: store.uploads,
    errors: errorsFor(widget),
    onChange: async (key, value) => {
      const next = draft();
      const target = next.widgets.find((item) => item.id === widget.id);
      target.options[key] = value;
      const error = await save(next, t.changed(label));
      if (error) rerender();
    },
  }));

  const geometry = h("fieldset", { class: "fieldset geometry" }, h("legend", { class: "field-label", text: t.position }));
  const grid = store.catalog.grid;
  for (const [key, labelText, max] of [["x", t.column, grid.columns], ["y", t.row, grid.rows], ["w", t.width, grid.columns], ["h", t.height, grid.rows]]) {
    const offset = key === "x" || key === "y" ? 1 : 0;
    const input = h("input", { class: "input input-number", type: "number", min: 1, max, step: 1, value: String(widget[key] + offset) });
    input.addEventListener("change", () => {
      const rect = { x: widget.x, y: widget.y, w: widget.w, h: widget.h, [key]: Math.round(Number(input.value)) - offset };
      if (!moveOrResize(widget, rect, kind, rerender)) {
        input.value = String(widget[key] + offset);
        toast(t.cannotMove, { tone: "error" });
      }
    });
    geometry.append(field(labelText, input));
  }
  panel.append(geometry);
  panel.append(button(t.removeTile, () => removeWidget(widget, rerender), { variant: "danger-quiet" }));
  return panel;
}

function addPanel(rerender) {
  const list = h("ul", { class: "add-list" });
  for (const [type, kind] of Object.entries(store.catalog.types)) {
    list.append(h("li", { class: "add-item" },
      h("div", {}, h("p", { class: "add-name", text: kind.label }), h("p", { class: "muted", text: kind.description })),
      button(t.addButton(kind.label), async () => {
        const spot = placeNew(store.settings.widgets, kind, store.catalog.grid);
        if (!spot) {
          toast(t.noSpace, { tone: "error" });
          return;
        }
        const widget = { id: newWidgetId(store.settings.widgets, type), type, ...spot, options: defaultOptions(kind) };
        store.selected = widget.id;
        await saveWidgets([...store.settings.widgets, widget], t.added(kind.label));
        rerender();
        document.querySelector(`.board-tile[data-widget="${widget.id}"]`)?.focus();
      }, { "aria-label": t.addButton(kind.label), class: "button button-secondary button-small" })));
  }
  return h("section", { class: "card" }, h("h2", { class: "card-title", text: t.addTitle }), list);
}

function templatesPanel(rerender) {
  const list = h("ul", { class: "add-list" });
  for (const template of TEMPLATES) {
    list.append(h("li", { class: "add-item" },
      h("div", {}, h("p", { class: "add-name", text: template.name }), h("p", { class: "muted", text: template.description })),
      button(t.apply, async () => {
        if (!(await confirmDialog(t.templateConfirm(template.name), t.apply))) return;
        store.selected = null;
        await saveWidgets(applyTemplate(template, store.settings.widgets, store.catalog), t.templateApplied(template.name));
        rerender();
      }, { "aria-label": t.applyTemplate(template.name), class: "button button-secondary button-small" })));
  }
  return h("section", { class: "card" }, h("h2", { class: "card-title", text: t.templatesTitle }), h("p", { class: "muted", text: t.templatesIntro }), list);
}

export function layoutView(container, status) {
  const rerender = () => {
    const focusedWidget = document.activeElement?.closest?.(".board-tile")?.dataset.widget;
    container.replaceChildren(render());
    if (focusedWidget) container.querySelector(`.board-tile[data-widget="${focusedWidget}"]`)?.focus({ preventScroll: true });
  };
  const render = () => {
    const switcher = h("div", { class: "segmented", role: "group", "aria-label": t.layoutTitle },
      button(t.viewGrid, () => { mode = "grid"; rerender(); }, { "aria-pressed": String(mode === "grid"), class: "segment" }),
      button(t.viewPreview, () => { mode = "preview"; rerender(); }, { "aria-pressed": String(mode === "preview"), class: "segment" }));
    const stage = h("section", { class: "stage card" },
      h("div", { class: "stage-head" }, h("h1", { class: "page-title", text: t.layoutTitle }), switcher),
      h("p", { class: "muted", text: t.layoutIntro }),
      mode === "grid" ? gridEditor(rerender, status) : preview(status));
    return h("div", { class: "layout-page" },
      stage,
      h("aside", { class: "layout-side" }, inspector(rerender)),
      h("div", { class: "layout-more" }, addPanel(rerender), templatesPanel(rerender)));
  };
  rerender();
  return rerender;
}
