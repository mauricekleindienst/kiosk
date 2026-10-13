// Small DOM helpers. Text always goes in through textContent, so feed content can never inject markup.

import { ICONS } from "./icons.js";

const SVG = "http://www.w3.org/2000/svg";

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

/** An icon from icons.js. Decorative unless a label is given. Unknown names draw a cloud. */
export function icon(name, className, label) {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", `icon ${className ?? ""}`.trim());
  svg.setAttribute("viewBox", "0 0 24 24");
  if (label) {
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
  } else {
    svg.setAttribute("aria-hidden", "true");
  }
  for (const [tag, attributes] of ICONS[name] ?? ICONS.cloudy) {
    const shape = document.createElementNS(SVG, tag);
    for (const [key, value] of Object.entries(attributes)) shape.setAttribute(key, String(value));
    svg.append(shape);
  }
  return svg;
}

export function clear(node) {
  node.replaceChildren();
  return node;
}
