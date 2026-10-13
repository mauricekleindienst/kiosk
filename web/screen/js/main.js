// Boots the screen: builds the tiles from the settings, ticks the clocks locally and asks the
// kiosk server every few seconds whether settings or data changed.

import { el } from "../../shared/js/dom.js";
import { zonedParts } from "../../shared/js/format.js";
import { isSleeping } from "../../shared/js/schedule.js";
import { strings } from "./strings.js";
import { WIDGETS } from "./widgets/index.js";

// A tiny local request; settings from the admin interface show up within this time.
const REVISION_POLL_MS = 3_000;
// The full state also comes once a minute, so ages and stale notices stay current.
const STATE_POLL_MS = 60_000;
const REQUEST_TIMEOUT_MS = 10_000;
const CLOCK_TICK_MS = 1_000;
// The daily reload clears whatever a browser accumulates over weeks; never right after a start.
const MIN_UPTIME_BEFORE_RELOAD_MS = 60 * 60_000;
const DEFAULT_TIME_ZONE = "Europe/Berlin";
// The screen itself reports its size, so the admin preview matches it; the preview does not.
const IS_PREVIEW = location.pathname.startsWith("/screen/");

const screenNode = document.getElementById("screen");
const overlay = document.getElementById("overlay");
const startedAt = Date.now();

let state = null;
let revision = null;
let reachable = true;
let tiles = [];
let lastMinute = "";
let builtFor = null;

const timeZone = () => state?.settings?.timeZone ?? DEFAULT_TIME_ZONE;
const uploadUrl = (id) => `/uploads/${encodeURIComponent(id)}`;

async function getJson(path) {
  const response = await fetch(path, { cache: "no-store", signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function applyAppearance(settings) {
  const root = document.documentElement;
  root.style.setProperty("--scale", String(settings.appearance.scale / 100));
  root.dataset.density = settings.appearance.density;
}

function build() {
  for (const tile of tiles) tile.instance.destroy?.();
  tiles = [];
  screenNode.replaceChildren();
  const settings = state.settings;
  applyAppearance(settings);
  const ctx = { settings, timeZone: settings.timeZone, uploadUrl };
  for (const widget of settings.widgets) {
    const module = WIDGETS[widget.type];
    if (!module) continue;
    const tile = el("section", `tile tile-${widget.type}`);
    tile.dataset.widget = widget.id;
    // Small tiles get less padding (screen.css); container queries cannot style the container itself.
    tile.dataset.rows = String(widget.h);
    tile.dataset.cols = String(widget.w);
    // Grid placement through the CSSOM; the CSP forbids style attributes, not this.
    tile.style.gridColumn = `${widget.x + 1} / span ${widget.w}`;
    tile.style.gridRow = `${widget.y + 1} / span ${widget.h}`;
    screenNode.append(tile);
    tiles.push({ widget, tile, instance: module.create(tile, widget, ctx) });
  }
  builtFor = state.revision.settings;
  const now = new Date();
  for (const { instance } of tiles) instance.tick?.(now);
  renderData(now);
}

function renderData(now) {
  for (const { instance } of tiles) instance.render(state, now, reachable);
}

function sleeping(now) {
  return isSleeping(state?.settings?.display?.sleep, zonedParts(now, timeZone()));
}

function renderOverlay(now) {
  const setup = !IS_PREVIEW && state?.setup;
  const asleep = !IS_PREVIEW && sleeping(now);
  document.body.classList.toggle("asleep", asleep);
  overlay.hidden = !setup || asleep;
  if (overlay.hidden) {
    overlay.replaceChildren();
    return;
  }
  const code = `${setup.code.slice(0, 3)} ${setup.code.slice(3)}`;
  const text = el("div", "overlay-text");
  text.append(el("p", "overlay-title", strings.setupTitle));
  text.append(el("p", "overlay-line", `${strings.setupText} ${setup.urls.join(" oder ")}`));
  const codeBlock = el("div", "overlay-code");
  codeBlock.append(el("span", "overlay-code-label", strings.setupCode), el("span", "overlay-code-value", code));
  overlay.replaceChildren(text, codeBlock);
}

async function maybeReload(now) {
  const reloadAt = state?.settings?.display?.reloadAt;
  if (IS_PREVIEW || !reloadAt || Date.now() - startedAt < MIN_UPTIME_BEFORE_RELOAD_MS) return;
  const { hour, minute } = zonedParts(now, timeZone());
  if (`${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}` !== reloadAt) return;
  // Reloading while the server is down would leave Chromium on an error page for good.
  try {
    await getJson("api/health");
    location.reload();
  } catch {
    // Server unreachable: keep the page; tomorrow is the next chance.
  }
}

function tick() {
  const now = new Date();
  for (const { instance } of tiles) instance.tick?.(now);
  const minute = `${now.getUTCHours()}:${now.getUTCMinutes()}`;
  if (minute !== lastMinute) {
    lastMinute = minute;
    if (state) renderData(now);
    renderOverlay(now);
    maybeReload(now);
  }
}

async function loadState() {
  try {
    state = await getJson("api/state");
    reachable = true;
  } catch {
    // The server restarts itself; until then the last data stays up with a stale notice.
    reachable = false;
  }
  if (!state) return;
  if (builtFor !== state.revision.settings) build();
  else renderData(new Date());
  renderOverlay(new Date());
}

async function pollRevision() {
  const size = IS_PREVIEW ? "" : `?w=${innerWidth}&h=${innerHeight}`;
  let next;
  try {
    next = await getJson(`api/revision${size}`);
  } catch {
    if (reachable) {
      reachable = false;
      if (state) renderData(new Date());
    }
    return;
  }
  const previous = revision;
  revision = next;
  // An admin's reload request, or a new server build after an update: load the new files.
  if (previous && (next.reload !== previous.reload || next.build !== previous.build)) {
    location.reload();
    return;
  }
  const changed = ["settings", "data", "setup"].some((key) => next[key] !== previous?.[key]);
  if (!reachable || !previous || changed) await loadState();
}

// What fits depends on the final font and the window size; lay out again when either changes.
document.fonts.ready.then(() => state && renderData(new Date()));
addEventListener("resize", () => state && build());

tick();
setInterval(tick, CLOCK_TICK_MS);
// The first revision request also tells the admin interface right away that the screen is up.
loadState().then(pollRevision);
setInterval(pollRevision, REVISION_POLL_MS);
setInterval(loadState, STATE_POLL_MS);
