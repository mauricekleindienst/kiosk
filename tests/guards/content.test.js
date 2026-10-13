// Rules over the pages, the texts, the templates and the contracts between server, screen and admin.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { TEMPLATES, applyTemplate } from "../../web/admin/js/templates.js";
import { t as adminStrings } from "../../web/admin/js/strings.js";
import { ICONS } from "../../web/shared/js/icons.js";
import { canPlace } from "../../web/shared/js/layout.js";
import { strings as screenStrings } from "../../web/screen/js/strings.js";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const catalog = JSON.parse(read("web/shared/widgets.json"));

test("pages have no inline scripts, styles or style attributes (CSP without unsafe-inline)", () => {
  for (const page of ["web/screen/index.html", "web/admin/index.html"]) {
    const html = read(page);
    assert.doesNotMatch(html, /<style/i, page);
    assert.doesNotMatch(html, /\sstyle=/i, page);
    assert.doesNotMatch(html, /\son[a-z]+=/i, `${page}: no inline event handlers`);
    for (const match of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/gi)) {
      assert.match(match[1], /\ssrc=/, `${page}: every script is a file`);
      assert.equal(match[2].trim(), "", `${page}: no inline script body`);
    }
  }
});

test("no innerHTML anywhere: feed text and settings only reach the page as text", () => {
  for (const file of ["web/screen/js/main.js", "web/screen/js/widgets/news.js", "web/screen/js/widgets/simple.js",
    "web/screen/js/widgets/weather.js", "web/screen/js/widgets/clock.js", "web/admin/js/ui.js", "web/admin/js/forms.js",
    "web/admin/js/layout-view.js", "web/admin/js/pages.js", "web/admin/js/app.js", "web/shared/js/dom.js"]) {
    assert.doesNotMatch(read(file), /innerHTML|outerHTML|insertAdjacentHTML|document\.write/, file);
  }
});

test("every weather icon the server can send has an icon and a German name", () => {
  const python = read("server/kiosk/weather.py");
  const block = python.match(/ICONS = \{([\s\S]*?)\}/)[1];
  const serverIcons = [...block.matchAll(/"([a-z-]+)"/g)].map((m) => m[1]);
  assert.ok(serverIcons.length >= 12);
  for (const name of serverIcons) {
    assert.ok(ICONS[name], `icons.js has no "${name}"`);
    assert.ok(screenStrings.conditions[name], `strings.conditions has no "${name}"`);
  }
});

test("every icon class is styled", () => {
  const css = read("web/screen/styles/screen.css");
  const classes = new Set(Object.values(ICONS).flatMap((shapes) => shapes.flatMap(([, attributes]) => attributes.class.split(" "))));
  for (const name of classes) assert.match(css, new RegExp(`\\.${name}\\b`), `screen.css does not style .${name}`);
});

test("every widget type has a screen module, and every option type has an admin control", () => {
  const registry = read("web/screen/js/widgets/index.js");
  const forms = read("web/admin/js/forms.js");
  for (const [type, kind] of Object.entries(catalog.types)) {
    assert.match(registry, new RegExp(`\\b${type}\\b`), `no screen module for "${type}"`);
    for (const option of kind.options) {
      if (["text", "url", "textarea"].includes(option.type)) continue;
      assert.match(forms, new RegExp(`"${option.type}"`), `no admin control for option type "${option.type}"`);
    }
  }
});

test("templates fit the grid, do not overlap, respect minimum sizes and keep content", () => {
  for (const template of TEMPLATES) {
    const current = [{ id: "news-main", type: "news", x: 0, y: 0, w: 1, h: 1, options: { title: "Rheinmetall", url: "https://example.org/feed" } }];
    const widgets = applyTemplate(template, current, catalog);
    const placed = [];
    for (const widget of widgets) {
      const kind = catalog.types[widget.type];
      assert.ok(kind, `${template.name}: unknown type ${widget.type}`);
      assert.ok(canPlace(placed, widget.id, widget, catalog.grid, kind.minSize), `${template.name}: ${widget.id} does not fit`);
      for (const key of Object.keys(widget.options)) {
        assert.ok(kind.options.some((option) => option.key === key), `${template.name}: unknown option ${widget.type}.${key}`);
      }
      placed.push(widget);
    }
    assert.equal(new Set(widgets.map((widget) => widget.id)).size, widgets.length, `${template.name}: duplicate ids`);
    const news = widgets.find((widget) => widget.type === "news");
    if (news) assert.equal(news.options.url, "https://example.org/feed", `${template.name}: keeps the existing feed`);
  }
});

function allTexts(value) {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(allTexts);
  if (typeof value === "function") {
    const args = Array(Math.max(value.length, 1)).fill("1");
    try {
      return [String(value(...args))];
    } catch {
      // Texts that take a list, like the places an image is used in.
      return [String(value(...args.map((arg) => [arg])))];
    }
  }
  return Object.values(value).flatMap(allTexts);
}

const catalogTexts = Object.values(catalog.types).flatMap((kind) => [
  kind.label, kind.description, ...kind.options.flatMap((option) => [option.label, option.help ?? "", ...(option.choices ?? []).map((c) => c.label)]),
]);

test("UI texts: no emoji, ellipsis right after the word, typographic dashes, Computer not Rechner", () => {
  for (const text of [...allTexts(screenStrings), ...allTexts(adminStrings), ...catalogTexts]) {
    assert.doesNotMatch(text, /\p{Extended_Pictographic}/u, `emoji in "${text}"`);
    assert.doesNotMatch(text, /\.\.\.| …/, `use "…" directly after the word: "${text}"`);
    assert.doesNotMatch(text, / - /, `use an en dash: "${text}"`);
    assert.doesNotMatch(text, /Rechner/, `glossary: "Computer", not "Rechner": "${text}"`);
    assert.doesNotMatch(text, /\bSie\b|\bIhr(e|en|em)?\b/, `the product says "du": "${text}"`);
  }
});

test("buttons that open a dialog end in an ellipsis", () => {
  for (const key of ["removeTile", "deleteImage", "upload"]) assert.match(adminStrings[key], /…$/, key);
  assert.match(adminStrings.applyTemplate("X"), /…$/);
});
