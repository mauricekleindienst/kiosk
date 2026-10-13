// The pages besides the layout: logo and images, settings, device.

import { newWidgetId, placeNew } from "../../shared/js/layout.js";
import { api } from "./api.js";
import { defaultOptions, timeZoneSelect } from "./forms.js";
import { draft, reloadUploads, save, store } from "./store.js";
import { LOCATION_PRESETS, t } from "./strings.js";
import { ago, button, confirmDialog, field, formatBytes, h, toast } from "./ui.js";

// Typed values wait this long before saving.
const TEXT_DEBOUNCE_MS = 700;
const STATUS_REFRESH_MS = 5_000;

function later(callback) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => callback(...args), TEXT_DEBOUNCE_MS);
  };
}

function card(title, ...children) {
  return h("section", { class: "card" }, h("h2", { class: "card-title", text: title }), ...children);
}

// Logo and images

async function uploadFiles(files, rerender) {
  let count = 0;
  for (const file of files) {
    toast(t.uploading(file.name));
    try {
      await api.upload(file);
      count += 1;
    } catch (error) {
      toast(`${file.name}: ${error.message}`, { tone: "error" });
      await reloadUploads();
      rerender();
      return;
    }
  }
  await reloadUploads();
  rerender();
  if (count) toast(t.uploaded(count));
}

function setLogo(id, rerender) {
  const next = draft();
  next.logo = id;
  save(next, id ? t.logoSet : t.logoCleared).then(rerender);
}

export function mediaView(container) {
  const rerender = () => container.replaceChildren(render());
  const render = () => {
    const logo = store.uploads.find((upload) => upload.id === store.settings.logo);
    const hasLogoTile = store.settings.widgets.some((widget) => widget.type === "logo");
    const logoCard = card(t.logoTitle,
      h("p", { class: "muted", text: t.logoIntro }),
      logo
        ? h("div", { class: "logo-current" }, h("img", { src: `/uploads/${logo.id}`, alt: logo.name }), h("p", { text: logo.name }))
        : h("p", { class: "muted", text: t.noLogo }),
      h("div", { class: "actions" },
        logo && !hasLogoTile ? button(t.addLogoTile, async () => {
          const kind = store.catalog.types.logo;
          const spot = placeNew(store.settings.widgets, kind, store.catalog.grid);
          if (!spot) {
            toast(t.noSpace, { tone: "error" });
            return;
          }
          const next = draft();
          next.widgets.push({ id: newWidgetId(next.widgets, "logo"), type: "logo", ...spot, options: defaultOptions(kind) });
          await save(next, t.added(kind.label));
          rerender();
        }) : null,
        logo ? button(t.removeLogo, () => setLogo(null, rerender), { variant: "link" }) : null));

    const input = h("input", { type: "file", accept: "image/png,image/jpeg,image/webp,image/gif,image/svg+xml", multiple: true, class: "visually-hidden", id: "upload-input" });
    input.addEventListener("change", () => uploadFiles([...input.files], rerender));
    const drop = h("div", { class: "dropzone" },
      h("label", { for: "upload-input", class: "button button-primary", text: t.upload }),
      h("p", { class: "muted", text: t.uploadHint }), input);
    drop.addEventListener("dragover", (event) => {
      event.preventDefault();
      drop.classList.add("is-over");
    });
    drop.addEventListener("dragleave", () => drop.classList.remove("is-over"));
    drop.addEventListener("drop", (event) => {
      event.preventDefault();
      drop.classList.remove("is-over");
      uploadFiles([...event.dataTransfer.files], rerender);
    });

    const list = h("ul", { class: "media-list" });
    for (const upload of store.uploads) {
      const isLogo = upload.id === store.settings.logo;
      list.append(h("li", { class: "media-item" },
        h("img", { class: "media-thumb", src: `/uploads/${upload.id}`, alt: "", loading: "lazy" }),
        h("div", { class: "media-text" },
          h("p", { class: "media-name", text: upload.name, title: upload.name }),
          h("p", { class: "muted", text: `${formatBytes(upload.size)} · ${upload.usedBy.length ? t.usedBy(upload.usedBy) : t.unused}` })),
        h("div", { class: "actions" },
          isLogo ? h("span", { class: "badge", text: t.isLogo }) : button(t.useAsLogo, () => setLogo(upload.id, rerender), { class: "button button-secondary button-small" }),
          button(t.deleteImage, async () => {
            if (!(await confirmDialog(t.deleteConfirm(upload.name), t.delete))) return;
            try {
              await api.deleteUpload(upload.id);
            } catch (error) {
              toast(error.message, { tone: "error" });
              return;
            }
            await reloadUploads();
            rerender();
          }, { variant: "danger-quiet", class: "button button-danger-quiet button-small", "aria-label": `${upload.name} ${t.delete}` }))));
    }
    return h("div", { class: "page" },
      h("h1", { class: "page-title", text: t.mediaTitle }),
      logoCard,
      card(t.imagesTitle, drop, store.uploads.length ? list : h("p", { class: "muted", text: t.noUploads })));
  };
  rerender();
  return rerender;
}

// Settings

export function settingsView(container) {
  const rerender = () => container.replaceChildren(render());
  const commit = (mutate, message) => {
    const next = draft();
    mutate(next);
    return save(next, message);
  };
  const errorAt = (path) => (store.lastError?.path === path ? store.lastError.message : null);
  const render = () => {
    const s = store.settings;

    const name = h("input", { class: "input", value: s.location.name, maxLength: 60 });
    const lat = h("input", { class: "input input-number", inputmode: "decimal", value: String(s.location.lat).replace(".", ",") });
    const lon = h("input", { class: "input input-number", inputmode: "decimal", value: String(s.location.lon).replace(".", ",") });
    const saveLocation = later(async () => {
      const parse = (input) => Number(input.value.trim().replace(",", "."));
      const error = await commit((next) => {
        next.location = { name: name.value, lat: parse(lat), lon: parse(lon) };
      }, t.saved);
      if (error) rerender();
    });
    for (const input of [name, lat, lon]) input.addEventListener("input", saveLocation);
    const preset = h("select", { class: "input" }, h("option", { value: "", text: t.locationPresetNone }),
      LOCATION_PRESETS.map((place) => h("option", { value: place.name, text: place.name })));
    preset.addEventListener("change", () => {
      const place = LOCATION_PRESETS.find((item) => item.name === preset.value);
      if (!place) return;
      commit((next) => {
        next.location = { ...place };
      }, t.saved).then(rerender);
    });
    const zone = timeZoneSelect(s.timeZone, (value) => commit((next) => {
      next.timeZone = value;
    }, t.saved));

    const scaleValue = h("output", { class: "range-value", text: t.scaleValue(s.appearance.scale) });
    const scale = h("input", { type: "range", class: "range", min: 80, max: 140, step: 5, value: String(s.appearance.scale) });
    scale.addEventListener("input", () => {
      scaleValue.textContent = t.scaleValue(scale.value);
    });
    scale.addEventListener("change", () => commit((next) => {
      next.appearance.scale = Number(scale.value);
    }, t.saved));
    const density = h("select", { class: "input" }, Object.entries(t.densities).map(([value, label]) => h("option", { value, text: label, selected: value === s.appearance.density })));
    density.addEventListener("change", () => commit((next) => {
      next.appearance.density = density.value;
    }, t.saved));

    const sleep = s.display.sleep;
    const sleepEnabled = h("input", { type: "checkbox", class: "switch", checked: sleep.enabled });
    sleepEnabled.addEventListener("change", () => commit((next) => {
      next.display.sleep.enabled = sleepEnabled.checked;
    }, t.saved).then(rerender));
    const from = h("input", { class: "input", type: "time", value: sleep.from, disabled: !sleep.enabled });
    const to = h("input", { class: "input", type: "time", value: sleep.to, disabled: !sleep.enabled });
    from.addEventListener("change", () => commit((next) => {
      next.display.sleep.from = from.value;
    }, t.saved));
    to.addEventListener("change", () => commit((next) => {
      next.display.sleep.to = to.value;
    }, t.saved));
    const weekends = h("input", { type: "checkbox", class: "switch", checked: sleep.weekends, disabled: !sleep.enabled });
    weekends.addEventListener("change", () => commit((next) => {
      next.display.sleep.weekends = weekends.checked;
    }, t.saved));
    const reloadAt = h("input", { class: "input", type: "time", value: s.display.reloadAt });
    reloadAt.addEventListener("change", () => commit((next) => {
      next.display.reloadAt = reloadAt.value;
    }, t.saved));

    return h("div", { class: "page" },
      h("h1", { class: "page-title", text: t.settingsTitle }),
      card(t.locationTitle,
        h("div", { class: "form" },
          field(t.locationPreset, preset),
          field(t.locationName, name, { error: errorAt("location.name") }),
          h("div", { class: "field-pair" },
            field(t.latitude, lat, { error: errorAt("location.lat") }),
            field(t.longitude, lon, { error: errorAt("location.lon") })),
          h("p", { class: "field-hint", text: t.coordinatesHint }),
          field(t.timeZone, zone, { error: errorAt("timeZone") }))),
      card(t.appearanceTitle,
        h("div", { class: "form" },
          h("div", { class: "field" }, h("label", { class: "field-label", for: "scale", text: t.scale }), h("div", { class: "range-row" }, Object.assign(scale, { id: "scale" }), scaleValue)),
          field(t.density, density))),
      card(t.displayTitle,
        h("div", { class: "form" },
          field(t.sleepEnabled, sleepEnabled, { inline: true, hint: t.sleepHint }),
          h("div", { class: "field-pair" }, field(t.sleepFrom, from), field(t.sleepTo, to)),
          field(t.sleepWeekends, weekends, { inline: true }),
          field(t.reloadAt, reloadAt, { hint: t.reloadHint }))));
  };
  rerender();
  return rerender;
}

// Device

export function deviceView(container) {
  let status = null;
  const rerender = () => container.replaceChildren(render());
  const refresh = async () => {
    try {
      status = await api.status();
    } catch (error) {
      toast(error.message, { tone: "error" });
    }
    rerender();
  };
  const render = () => {
    if (!status) return h("div", { class: "page" }, h("h1", { class: "page-title", text: t.deviceTitle }));
    const screen = status.screen;
    const sources = h("ul", { class: "source-list" });
    for (const source of status.sources) {
      const state = source.error ? t.sourceError(source.error) : source.fetchedAt ? t.sourceOk(ago(source.fetchedAt)) : t.sourcePending;
      sources.append(h("li", { class: source.error ? "source source-error" : "source" }, h("p", { class: "source-label", text: source.label }), h("p", { class: "muted", text: state })));
    }
    const current = h("input", { class: "input", type: "password", autocomplete: "current-password", required: true });
    const next = h("input", { class: "input", type: "password", autocomplete: "new-password", minLength: 8, required: true });
    const passwordField = field(t.newPassword, next, { hint: t.setupPasswordHint });
    const form = h("form", { class: "form" },
      field(t.currentPassword, current), passwordField,
      h("div", { class: "actions" }, button(t.savePassword, null, { variant: "primary", type: "submit" })));
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api.changePassword(current.value, next.value);
        form.reset();
        passwordField.setError(null);
        toast(t.passwordChanged);
      } catch (error) {
        passwordField.setError(error.message);
      }
    });

    return h("div", { class: "page" },
      h("h1", { class: "page-title", text: t.deviceTitle }),
      card(t.screenTitle,
        h("p", { text: screen ? t.screenConnected(screen.width, screen.height, ago(screen.lastSeen)) : t.screenMissing }),
        h("div", { class: "actions" },
          button(t.reloadScreen, async () => {
            await api.reloadScreen();
            toast(t.reloadedScreen);
          }),
          button(t.refreshNow, async () => {
            await api.refresh();
            toast(t.refreshed);
            setTimeout(refresh, 3000);
          }))),
      card(t.sourcesTitle, sources),
      card(t.addressesTitle, h("ul", { class: "plain-list" }, status.addresses.map((url) => h("li", { text: url }))),
        h("p", { class: "muted", text: t.version(status.version, ago(status.startedAt)) })),
      card(t.passwordTitle, form));
  };
  rerender();
  refresh();
  // Keep the status current while the page is open; stop once another page replaced it.
  const timer = setInterval(() => {
    if (!container.isConnected) {
      clearInterval(timer);
      return;
    }
    if (!container.contains(document.activeElement)) refresh();
  }, STATUS_REFRESH_MS);
  return refresh;
}
