// Rules over the page, the texts and the contract between server and screen.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { ICONS } from "../../web/js/icons.js";
import { strings } from "../../web/js/strings.js";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");

test("index.html has no inline scripts, styles or style attributes (CSP without unsafe-inline)", () => {
  const html = read("web/index.html");
  assert.doesNotMatch(html, /<style/i);
  assert.doesNotMatch(html, /\sstyle=/i);
  assert.doesNotMatch(html, /\son[a-z]+=/i, "no inline event handlers");
  for (const match of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/gi)) {
    assert.match(match[1], /\ssrc=/, "every script is a file");
    assert.equal(match[2].trim(), "", "no inline script body");
  }
});

test("every weather icon the server can send has an icon and a German name", () => {
  const python = read("server/kiosk/weather.py");
  const block = python.match(/ICONS = \{([\s\S]*?)\}/)[1];
  const serverIcons = [...block.matchAll(/"([a-z-]+)"/g)].map((m) => m[1]);
  assert.ok(serverIcons.length >= 12);
  for (const name of serverIcons) {
    assert.ok(ICONS[name], `icons.js has no "${name}"`);
    assert.ok(strings.conditions[name], `strings.conditions has no "${name}"`);
  }
});

test("every icon class is styled", () => {
  const css = read("web/styles/app.css");
  const classes = new Set(
    Object.values(ICONS).flatMap((shapes) => shapes.flatMap(([, attributes]) => attributes.class.split(" "))),
  );
  for (const name of classes) assert.match(css, new RegExp(`\\.${name}\\b`), `app.css does not style .${name}`);
});

function allTexts(value) {
  if (typeof value === "string") return [value];
  if (typeof value === "function") return [String(value(...Array(value.length).fill("1")))];
  return Object.values(value).flatMap(allTexts);
}

test("UI texts: no emoji, ellipsis right after the word, typographic dashes", () => {
  for (const text of allTexts(strings)) {
    assert.doesNotMatch(text, /\p{Extended_Pictographic}/u, `emoji in "${text}"`);
    assert.doesNotMatch(text, /\.\.\.| …/, `use "…" directly after the word: "${text}"`);
    assert.doesNotMatch(text, / - /, `use an en dash: "${text}"`);
  }
});

test("the glossary: Computer, not Rechner", () => {
  for (const text of allTexts(strings)) assert.doesNotMatch(text, /Rechner/);
});
