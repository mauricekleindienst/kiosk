// Boots the screen: the clock ticks locally, the data comes from the kiosk server every minute.

import { formatClock, formatLongDate, isoDay, isoWeek, zonedParts } from "./format.js";
import { nextHoliday } from "./holidays.js";
import { renderNews } from "./news-view.js";
import { renderStatus } from "./status.js";
import { strings } from "./strings.js";
import { renderWeather } from "./weather-view.js";

const POLL_MS = 60_000;
const REQUEST_TIMEOUT_MS = 10_000;
const CLOCK_TICK_MS = 1_000;
// The daily reload clears whatever a browser accumulates over weeks; never right after a start.
const MIN_UPTIME_BEFORE_RELOAD_MS = 60 * 60_000;
const DEFAULT_TIME_ZONE = "Europe/Berlin";

const $ = (id) => document.getElementById(id);
const nodes = {
  timePanel: $("time-panel"),
  clock: $("clock"),
  date: $("date"),
  dateMeta: $("date-meta"),
  weatherTitle: $("weather-title"),
  weatherStatus: $("weather-status"),
  weatherBody: $("weather-body"),
  weatherSource: $("weather-source"),
  mainTitle: $("news-main-title"),
  mainStatus: $("news-main-status"),
  mainBody: $("news-main-body"),
  sideTitle: $("news-side-title"),
  sideStatus: $("news-side-status"),
  sideBody: $("news-side-body"),
};

const startedAt = Date.now();
let state = null;
let serverReachable = true;
let lastMinute = "";

function timeZone() {
  return state?.timeZone ?? DEFAULT_TIME_ZONE;
}

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function renderDate(now) {
  const tz = timeZone();
  const today = isoDay(now, tz);
  setText(nodes.date, formatLongDate(now, tz));
  const holiday = nextHoliday(today);
  let holidayText;
  if (holiday.daysUntil === 0) holidayText = strings.holidayToday(holiday.name);
  else if (holiday.daysUntil === 1) holidayText = strings.holidayTomorrow(holiday.name);
  else holidayText = strings.holidayIn(holiday.name, holiday.daysUntil);
  setText(nodes.dateMeta, `${strings.calendarWeek(isoWeek(today))} · ${holidayText}`);
}

// Shown until the first answer from the server: every block says it is loading.
const NOTHING_YET = {
  weather: { data: null, error: null },
  news: { main: { title: "", data: null, error: null }, side: { title: "", data: null, error: null } },
};

function renderData(now) {
  const tz = timeZone();
  const { weather, news } = state ?? NOTHING_YET;
  setText(nodes.weatherTitle, strings.weatherTitle(weather.data?.location ?? ""));
  renderStatus(nodes.weatherStatus, weather, now, serverReachable, tz);
  renderWeather(nodes.weatherBody, weather, tz, now);
  // The regional block sizes itself; the main news then fills what is left, so it renders last.
  setText(nodes.sideTitle, news.side.title);
  renderStatus(nodes.sideStatus, news.side, now, serverReachable, tz);
  renderNews(nodes.sideBody, news.side, now);
  setText(nodes.mainTitle, news.main.title);
  renderStatus(nodes.mainStatus, news.main, now, serverReachable, tz);
  renderNews(nodes.mainBody, news.main, now, { lead: true });
}

async function maybeReload(now) {
  const reloadAt = state?.display?.reloadAt;
  if (!reloadAt || Date.now() - startedAt < MIN_UPTIME_BEFORE_RELOAD_MS) return;
  const { hour, minute } = zonedParts(now, timeZone());
  if (`${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}` !== reloadAt) return;
  // Reloading while the server is down would leave Chromium on an error page for good.
  try {
    const response = await fetch("/api/health", { cache: "no-store", signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
    if (response.ok) location.reload();
  } catch {
    // Server unreachable: keep the page; tomorrow is the next chance.
  }
}

// Ticks every second but touches the page only when the minute changes, so the screen stays idle.
function tick() {
  const now = new Date();
  setText(nodes.clock, formatClock(now, timeZone()));
  const minute = `${isoDay(now, timeZone())} ${formatClock(now, timeZone())}`;
  if (minute !== lastMinute) {
    lastMinute = minute;
    renderDate(now);
    renderData(now);
    maybeReload(now);
  }
}

async function poll() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch("/api/state", { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state = await response.json();
    serverReachable = true;
  } catch {
    // The server restarts itself; until then the last data stays up with a stale notice.
    serverReachable = false;
  } finally {
    clearTimeout(timer);
  }
  renderData(new Date());
}

nodes.timePanel.setAttribute("aria-label", strings.timeRegion);
nodes.weatherSource.textContent = strings.weatherSource;
tick();
setInterval(tick, CLOCK_TICK_MS);
// What fits depends on the final font and the window size; lay out again when either changes.
document.fonts.ready.then(() => renderData(new Date()));
addEventListener("resize", () => renderData(new Date()));
poll();
setInterval(poll, POLL_MS);
