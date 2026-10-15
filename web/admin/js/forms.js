// Builds the settings form of a widget from its options in the catalog (shared/widgets.json).
// Changes apply right away: toggles and lists at once, typed text after a short pause.

import { api } from "./api.js";
import { button, field, h, uid } from "./ui.js";
import { t } from "./strings.js";

// Typing waits this long before saving, so a word is one change and not one per letter.
const TEXT_DEBOUNCE_MS = 700;

function todayIso() {
  return new Date().toLocaleDateString("en-CA");
}

let zoneNames = null;
function timeZones() {
  zoneNames ??= Intl.supportedValuesOf ? Intl.supportedValuesOf("timeZone") : ["Europe/Berlin"];
  return zoneNames;
}

export function timeZoneSelect(value, onChange) {
  const select = h("select", { class: "input", onChange: () => onChange(select.value) });
  for (const zone of timeZones()) select.append(h("option", { value: zone, text: zone.replaceAll("_", " "), selected: zone === value }));
  if (!timeZones().includes(value)) select.prepend(h("option", { value, text: value, selected: true }));
  return select;
}

function debounced(callback) {
  let timer = null;
  const run = (value) => {
    clearTimeout(timer);
    timer = setTimeout(() => callback(value), TEXT_DEBOUNCE_MS);
  };
  run.flush = (value) => {
    clearTimeout(timer);
    callback(value);
  };
  return run;
}

function textControl(spec, value, commit) {
  const multiline = spec.type === "textarea";
  const input = h(multiline ? "textarea" : "input", {
    class: "input",
    value: value ?? "",
    maxLength: spec.maxLength ?? (spec.type === "url" ? 2000 : 200),
    rows: multiline ? 4 : null,
    type: multiline ? null : spec.type === "url" ? "url" : "text",
    spellcheck: spec.type !== "url",
    autocomplete: "off",
  });
  const later = debounced(commit);
  input.addEventListener("input", () => later(input.value));
  input.addEventListener("change", () => later.flush(input.value));
  return input;
}

function imageControl(spec, value, commit, uploads) {
  // "accept" limits the choice to some formats; upload ids end in the format the server detected.
  const choices = spec.accept ? uploads.filter((upload) => spec.accept.includes(upload.id.split(".").pop())) : uploads;
  const select = h("select", { class: "input", onChange: () => commit(select.value || null) });
  select.append(h("option", { value: "", text: spec.accept ? t.noImageChosen : t.companyLogo, selected: !value }));
  for (const upload of choices) select.append(h("option", { value: upload.id, text: upload.name, selected: upload.id === value }));
  return select;
}

function imagesControl(spec, value, commit, uploads) {
  if (!uploads.length) return h("p", { class: "field-hint", text: t.noImagesYet });
  const chosen = new Set(value);
  const list = h("div", { class: "image-picker", role: "group" });
  for (const upload of uploads) {
    const checkbox = h("input", {
      type: "checkbox",
      checked: chosen.has(upload.id),
      onChange: () => {
        if (checkbox.checked) chosen.add(upload.id);
        else chosen.delete(upload.id);
        // Keep the order of the upload list, which is the order of the slideshow.
        commit(uploads.map((item) => item.id).filter((id) => chosen.has(id)));
      },
    });
    list.append(h("label", { class: "image-choice" }, checkbox, h("img", { src: `/uploads/${upload.id}`, alt: "", loading: "lazy" }), h("span", { text: upload.name })));
  }
  return list;
}

function zonesControl(spec, value, commit) {
  const zones = structuredClone(value);
  const wrapper = h("div", { class: "zones-editor" });
  const render = () => {
    wrapper.replaceChildren();
    zones.forEach((zone, index) => {
      const label = h("input", { class: "input", value: zone.label, maxLength: 40, "aria-label": t.zoneLabel });
      const later = debounced(() => commit(structuredClone(zones)));
      label.addEventListener("input", () => {
        zone.label = label.value;
        later();
      });
      const zoneSelect = timeZoneSelect(zone.timeZone, (next) => {
        zone.timeZone = next;
        commit(structuredClone(zones));
      });
      zoneSelect.setAttribute("aria-label", t.zoneTimeZone);
      const remove = button(t.removeZone, () => {
        zones.splice(index, 1);
        commit(structuredClone(zones));
        render();
      }, { variant: "link" });
      wrapper.append(h("div", { class: "zone-row" }, label, zoneSelect, remove));
    });
    if (zones.length < (spec.maxItems ?? 6)) {
      wrapper.append(button(t.addZone, () => {
        zones.push({ label: "Berlin", timeZone: "Europe/Berlin" });
        commit(structuredClone(zones));
        render();
      }));
    }
  };
  render();
  return wrapper;
}

function stopControl(spec, value, commit) {
  const wrapper = h("div", { class: "stop-picker" });
  const current = h("p", { class: value ? "stop-current" : "field-hint", text: value ? value.name : t.noStopYet });
  const input = h("input", { class: "input", type: "search", placeholder: t.stopSearchPlaceholder, autocomplete: "off", "aria-label": t.stopSearch });
  const results = h("ul", { class: "stop-results", role: "listbox", "aria-label": t.stopResults });
  const message = h("p", { class: "field-hint", role: "status" });
  let counter = 0;
  const search = async () => {
    const text = input.value.trim();
    results.replaceChildren();
    if (text.length < 2) {
      message.textContent = "";
      return;
    }
    const mine = (counter += 1);
    message.textContent = t.stopSearching;
    try {
      const { stops } = await api.searchStops(text);
      // A slower, older answer must not replace a newer one.
      if (mine !== counter) return;
      message.textContent = stops.length ? "" : t.stopNothingFound;
      for (const stop of stops) {
        results.append(h("li", {}, button(stop.name, () => {
          commit({ id: stop.id, name: stop.name });
          current.className = "stop-current";
          current.textContent = stop.name;
          results.replaceChildren();
          input.value = "";
        }, { class: "stop-result" })));
      }
    } catch (error) {
      if (mine === counter) message.textContent = error.message;
    }
  };
  const later = debounced(search);
  input.addEventListener("input", () => later());
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      later.flush();
    }
  });
  wrapper.append(current, input, message, results);
  return wrapper;
}

function productsControl(spec, value, commit) {
  const chosen = new Set(value);
  const group = h("div", { class: "check-grid", role: "group" });
  for (const choice of spec.choices) {
    const box = h("input", {
      type: "checkbox",
      checked: chosen.has(choice.value),
      onChange: () => {
        if (box.checked) chosen.add(choice.value);
        else chosen.delete(choice.value);
        commit(spec.choices.map((item) => item.value).filter((item) => chosen.has(item)));
      },
    });
    group.append(h("label", { class: "check" }, box, h("span", { text: choice.label })));
  }
  return group;
}

/** The form for one widget. `onChange(key, value)` saves; `errors` maps option keys to messages. */
export function widgetForm(kind, widget, { onChange, uploads, errors = {} }) {
  const form = h("div", { class: "form" });
  for (const spec of kind.options) {
    const value = widget.options[spec.key];
    const commit = (next) => onChange(spec.key, next);
    let control;
    let inline = false;
    switch (spec.type) {
      case "boolean":
        control = h("input", { type: "checkbox", class: "switch", checked: Boolean(value), onChange: () => commit(control.checked) });
        inline = true;
        break;
      case "select":
        control = h("select", { class: "input", onChange: () => commit(control.value) });
        for (const choice of spec.choices) control.append(h("option", { value: choice.value, text: choice.label, selected: choice.value === value }));
        break;
      case "number":
        control = h("input", { class: "input input-number", type: "number", min: spec.min, max: spec.max, step: 1, value: String(value) });
        control.addEventListener("change", () => {
          const number = Math.round(Number(control.value));
          if (Number.isFinite(number)) commit(Math.min(spec.max, Math.max(spec.min, number)));
        });
        break;
      case "date": {
        control = h("input", { class: "input", type: "date", value: value ?? "", onChange: () => commit(control.value || null) });
        const todayButton = button(t.today, () => {
          control.value = todayIso();
          commit(control.value);
        }, { variant: "link" });
        form.append(h("div", { class: "field-row" }, field(spec.label, control, { hint: spec.help, error: errors[spec.key] }), todayButton));
        continue;
      }
      case "time":
        control = h("input", { class: "input", type: "time", value, onChange: () => commit(control.value) });
        break;
      case "image":
        control = imageControl(spec, value, commit, uploads);
        break;
      case "images":
        form.append(h("fieldset", { class: "fieldset" }, h("legend", { class: "field-label", text: spec.label }), imagesControl(spec, value, commit, uploads)));
        continue;
      case "stop":
        form.append(h("fieldset", { class: "fieldset" }, h("legend", { class: "field-label", text: spec.label }), stopControl(spec, value, commit),
          errors[spec.key] ? h("p", { class: "field-error", role: "alert", text: errors[spec.key] }) : null));
        continue;
      case "products":
        form.append(h("fieldset", { class: "fieldset" }, h("legend", { class: "field-label", text: spec.label }), productsControl(spec, value, commit),
          errors[spec.key] ? h("p", { class: "field-error", role: "alert", text: errors[spec.key] }) : null));
        continue;
      case "zones":
        form.append(h("fieldset", { class: "fieldset" }, h("legend", { class: "field-label", text: spec.label }), zonesControl(spec, value, commit)));
        continue;
      default:
        control = textControl(spec, value, commit);
    }
    control.id ||= uid(`opt-${spec.key}`);
    form.append(field(spec.label, control, { hint: spec.help, error: errors[spec.key], inline }));
  }
  return form;
}

/** Defaults for a new widget, with sensible dates where the catalog has none. */
export function defaultOptions(kind) {
  const options = {};
  for (const spec of kind.options) {
    let value = structuredClone(spec.default ?? null);
    if (spec.type === "date" && value == null && spec.required) {
      const date = new Date();
      // A countdown starts a month ahead; a "days since" counter starts today.
      if (spec.key === "date") date.setDate(date.getDate() + 30);
      value = date.toLocaleDateString("en-CA");
    }
    options[spec.key] = value;
  }
  return options;
}
