// Design rules from the guidelines as cheap static checks: rules that are not tested come back.

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";

const STYLES = new URL("../../web/styles/", import.meta.url);
const sheets = readdirSync(STYLES)
  .filter((name) => name.endsWith(".css"))
  .map((name) => ({ name, css: readFileSync(new URL(name, STYLES), "utf8").replace(/\/\*[\s\S]*?\*\//g, "") }));

function rules(css) {
  const found = [];
  const pattern = /([^{}]+)\{([^{}]*)\}/g;
  for (const match of css.matchAll(pattern)) {
    const declarations = match[2]
      .split(";")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const colon = line.indexOf(":");
        return { property: line.slice(0, colon).trim(), value: line.slice(colon + 1).trim() };
      });
    found.push({ selector: match[1].trim(), declarations });
  }
  return found;
}

const others = sheets.filter((sheet) => sheet.name !== "tokens.css");

test("stylesheets have balanced braces and no merge markers", () => {
  for (const { name, css } of sheets) {
    assert.equal((css.match(/\{/g) ?? []).length, (css.match(/\}/g) ?? []).length, `${name}: unbalanced braces`);
    assert.doesNotMatch(css, /^(<<<<<<<|=======|>>>>>>>)/m, `${name}: merge marker`);
  }
});

test("literal colors only in tokens.css", () => {
  for (const { name, css } of others) {
    assert.doesNotMatch(css, /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(|oklch\(/i, `${name} has a literal color; add a token`);
  }
});

test("weights, layers and pill radii come from tokens", () => {
  for (const { name, css } of others) {
    for (const { selector, declarations } of rules(css)) {
      // A @font-face rule declares the weight range a font file covers, not a weight in use.
      if (selector === "@font-face") continue;
      for (const { property, value } of declarations) {
        if (property === "font-weight") assert.match(value, /^var\(--weight-/, `${name} ${selector}: font-weight ${value}`);
        if (property === "z-index") assert.match(value, /^var\(/, `${name} ${selector}: z-index ${value}`);
        if (property === "border-radius") assert.doesNotMatch(value, /999|9999|50%/, `${name} ${selector}: use --radius-pill`);
      }
    }
  }
});

test("no accent or status frames on states", () => {
  const STATE = /\.(active|selected|sel|current|on|checked|picked|now|today|focused|is-selected|running|live|playing)\b|:checked|:hover|:focus(-visible|-within)?\b|\[aria-(selected|current|pressed|checked)/;
  const FRAME = /^(border(-\w+)*|outline(-color)?|box-shadow)$/;
  const ACCENT = /--(accent[\w-]*|success|warning|danger|info|icon-[\w-]+|temp-[\w-]+)\b/;
  for (const { name, css } of sheets) {
    for (const { selector, declarations } of rules(css)) {
      if (!STATE.test(selector)) continue;
      for (const { property, value } of declarations) {
        assert.ok(!(FRAME.test(property) && ACCENT.test(value)), `${name} ${selector}: ${property}: ${value}`);
      }
    }
  }
});

test("no colored bars on the left", () => {
  for (const { name, css } of sheets) {
    for (const { selector, declarations } of rules(css)) {
      for (const { property } of declarations) {
        assert.ok(!/^border-(left|inline-start)/.test(property), `${name} ${selector}: ${property}`);
      }
    }
  }
});

test("the focus ring is the neutral token", () => {
  for (const { name, css } of others) {
    for (const { selector, declarations } of rules(css)) {
      for (const { property, value } of declarations) {
        if (/^outline(-color)?$/.test(property) && value !== "none") {
          assert.match(value, /var\(--focus-ring\)/, `${name} ${selector}: ${property}: ${value}`);
        }
      }
    }
  }
});

// WCAG 2.x relative luminance and contrast ratio.
const tokens = Object.fromEntries(
  [...readFileSync(new URL("tokens.css", STYLES), "utf8").matchAll(/(--[\w-]+):\s*(#[0-9a-f]{6})\b/gi)].map((m) => [m[1], m[2]]),
);

function luminance(hex) {
  const channel = (i) => {
    const value = parseInt(hex.slice(i, i + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

function contrast(a, b) {
  const [light, dark] = [luminance(tokens[a]), luminance(tokens[b])].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

test("text meets WCAG AA on every background it sits on", () => {
  const pairs = [
    ...["--text", "--text-muted", "--text-subtle"].flatMap((text) =>
      ["--surface", "--surface-sunken", "--bg-page"].map((bg) => [text, bg])),
    ["--text", "--warning-soft"],
    ["--text", "--danger-soft"],
    ["--warning", "--warning-soft"],
    ["--danger", "--danger-soft"],
    ["--icon-rain", "--surface"],
    ["--icon-rain", "--surface-sunken"],
  ];
  for (const [text, bg] of pairs) {
    const ratio = contrast(text, bg);
    assert.ok(ratio >= 4.5, `${text} on ${bg}: ${ratio.toFixed(2)}:1, needs 4.5:1`);
  }
});

test("meaningful fills reach 3:1 against the panel", () => {
  for (const fill of ["--temp-cold", "--temp-warm", "--icon-bolt", "--icon-snow", "--icon-hail", "--warning", "--danger", "--icon-rain"]) {
    const ratio = contrast(fill, "--surface");
    assert.ok(ratio >= 3, `${fill} on --surface: ${ratio.toFixed(2)}:1, needs 3:1`);
  }
});
