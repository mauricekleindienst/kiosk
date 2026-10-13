// Small UI building blocks: elements, form fields, the confirm dialog and the toast with undo.

import { t } from "./strings.js";

let idCounter = 0;
export const uid = (prefix) => `${prefix}-${(idCounter += 1)}`;

export function h(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key in node && typeof value !== "string") node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) if (child != null && child !== false) node.append(child);
  return node;
}

/** A labelled field. `control` is the input; hint and error get ids for aria-describedby. */
export function field(label, control, { hint, error, inline = false } = {}) {
  const id = control.id || uid("field");
  control.id = id;
  const hintNode = hint ? h("p", { class: "field-hint", id: `${id}-hint`, text: hint }) : null;
  const errorNode = h("p", { class: "field-error", id: `${id}-error`, role: "alert", text: error ?? "" });
  errorNode.hidden = !error;
  control.setAttribute("aria-describedby", [hintNode && hintNode.id, errorNode.id].filter(Boolean).join(" "));
  if (error) control.setAttribute("aria-invalid", "true");
  const labelNode = h("label", { class: "field-label", for: id, text: label });
  const wrapper = h("div", { class: inline ? "field field-inline" : "field" }, inline ? [control, labelNode] : [labelNode, control], hintNode, errorNode);
  wrapper.setError = (message) => {
    errorNode.textContent = message ?? "";
    errorNode.hidden = !message;
    if (message) control.setAttribute("aria-invalid", "true");
    else control.removeAttribute("aria-invalid");
  };
  return wrapper;
}

export function button(text, onClick, { variant = "secondary", type = "button", ...rest } = {}) {
  return h("button", { class: `button button-${variant}`, type, text, onClick, ...rest });
}

/** Asks before something destructive. Resolves true only on the explicit confirm button. */
export function confirmDialog(message, confirmLabel) {
  return new Promise((resolve) => {
    const previous = document.activeElement;
    const dialog = h("dialog", { class: "dialog" });
    const cancel = button(t.cancel, () => dialog.close("cancel"));
    const confirm = button(confirmLabel, () => dialog.close("confirm"), { variant: "danger" });
    dialog.append(h("p", { class: "dialog-text", text: message }), h("div", { class: "dialog-actions" }, cancel, confirm));
    dialog.addEventListener("close", () => {
      dialog.remove();
      previous?.focus?.();
      resolve(dialog.returnValue === "confirm");
    });
    document.body.append(dialog);
    dialog.showModal();
    // Destructive confirmations start on "Cancel"; Enter does not delete.
    cancel.focus();
  });
}

let toastTimer = null;

/** One quiet message at the bottom, optionally with an undo button. */
export function toast(message, { undo, tone = "neutral" } = {}) {
  const region = document.getElementById("toasts");
  clearTimeout(toastTimer);
  const node = h("div", { class: `toast toast-${tone}` }, h("span", { text: message }));
  if (undo) {
    node.append(button(t.undo, async () => {
      node.remove();
      await undo();
    }, { variant: "link" }));
  }
  region.replaceChildren(node);
  toastTimer = setTimeout(() => node.remove(), undo ? 10_000 : 5_000);
}

export function formatBytes(bytes) {
  const format = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });
  if (bytes < 1024 * 1024) return `${format.format(bytes / 1024)} KB`;
  return `${format.format(bytes / (1024 * 1024))} MB`;
}

export function ago(isoString) {
  if (!isoString) return "";
  return t.ago(Math.max(0, Math.floor((Date.now() - Date.parse(isoString)) / 60000)));
}
