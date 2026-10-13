// The admin's copy of the settings. Every change is saved right away, one save after the other,
// and offers undo. A conflict (someone else saved) loads the current state from the server.

import { api, ApiError } from "./api.js";
import { t } from "./strings.js";
import { toast } from "./ui.js";

const listeners = new Set();
let queue = Promise.resolve();

export const store = {
  catalog: null,
  settings: null,
  revision: 0,
  uploads: [],
  selected: null,
  lastError: null,
};

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function notify() {
  for (const listener of [...listeners]) listener(store);
}

export async function loadAll() {
  const [catalog, settings, uploads] = await Promise.all([api.catalog(), api.settings(), api.uploads()]);
  store.catalog = catalog;
  store.settings = settings.settings;
  store.revision = settings.revision;
  store.uploads = uploads.uploads;
}

export async function reloadUploads() {
  store.uploads = (await api.uploads()).uploads;
  notify();
}

/**
 * Saves `next` (a full settings object). Shows `message` with an undo that restores the
 * settings from before. Resolves to the error, if any, so forms can show it at the field.
 */
export function save(next, message, { undoable = true } = {}) {
  const before = store.settings;
  store.settings = next;
  store.lastError = null;
  notify();
  const run = queue.then(async () => {
    try {
      const saved = await api.saveSettings(next, store.revision);
      store.settings = saved.settings;
      store.revision = saved.revision;
      notify();
      if (message) toast(message, undoable ? { undo: () => save(before, t.undone, { undoable: false }) } : {});
      return null;
    } catch (error) {
      if (error instanceof ApiError && error.status === 409 && error.body?.settings) {
        store.settings = error.body.settings;
        store.revision = error.body.revision;
      } else {
        store.settings = before;
      }
      store.lastError = error;
      notify();
      toast(error.message, { tone: "error" });
      return error;
    }
  });
  queue = run.then(() => undefined);
  return run;
}

/** A deep copy to change without touching the saved state. */
export function draft() {
  return structuredClone(store.settings);
}

export function widgetLabel(widget) {
  const kind = store.catalog.types[widget.type];
  const detail = widget.options.title ?? widget.options.label;
  return detail && detail !== kind.label ? `${kind.label}: ${detail}` : kind.label;
}
