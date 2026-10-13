// Starts the real kiosk server against a fake Bright Sky and a fake news feed, for e2e tests and
// screenshots. The fake data is generated relative to the current time and is clearly test data.

import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";

const KIOSK_PORT = Number(process.env.KIOSK_E2E_PORT ?? 8199);
const ADMIN_PORT = Number(process.env.KIOSK_E2E_ADMIN_PORT ?? 8198);
const ROOT = new URL("../../", import.meta.url).pathname;

const DAY_ICONS = ["partly-cloudy-day", "rain", "cloudy", "clear-day", "thunderstorm", "snow", "fog", "sleet"];

function berlinMidnight(now) {
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Berlin" }).format(now);
  // Berlin is UTC+1 or UTC+2; find the instant whose Berlin date starts the day.
  for (const offset of [2, 1]) {
    const candidate = new Date(`${day}T00:00:00+0${offset}:00`);
    if (new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Berlin", hour: "2-digit", hourCycle: "h23" }).format(candidate) === "00") {
      return candidate;
    }
  }
  return new Date(`${day}T00:00:00Z`);
}

function forecast(now) {
  const start = berlinMidnight(now);
  const weather = [];
  for (let hour = 0; hour < 24 * 9; hour += 1) {
    const moment = new Date(start.getTime() + hour * 3600_000);
    const day = Math.floor(hour / 24);
    const clockHour = hour % 24;
    const night = clockHour < 7 || clockHour > 19;
    let icon = DAY_ICONS[day % DAY_ICONS.length];
    if (night && icon === "clear-day") icon = "clear-night";
    if (night && icon === "partly-cloudy-day") icon = "partly-cloudy-night";
    const wet = ["rain", "thunderstorm", "snow", "sleet"].includes(icon);
    weather.push({
      timestamp: moment.toISOString(),
      temperature: Math.round((9 - day * 1.6 + 6 * Math.sin(((clockHour - 9) / 24) * 2 * Math.PI)) * 10) / 10,
      icon,
      condition: wet ? "rain" : "dry",
      precipitation: wet ? 0.6 : 0,
      precipitation_probability: wet ? 70 : clockHour % 5 === 0 ? 30 : 5,
      wind_speed: 14,
      relative_humidity: 76,
    });
  }
  return { weather, sources: [] };
}

function current(now) {
  return {
    weather: {
      timestamp: now.toISOString(),
      temperature: 12.4,
      icon: "partly-cloudy-day",
      condition: "dry",
      wind_speed_10: 14.2,
      wind_gust_speed_10: 31.5,
      relative_humidity: 74,
      precipitation_60: 0,
    },
    sources: [],
  };
}

function alerts(now) {
  return {
    alerts: [
      {
        severity: "minor",
        status: "actual",
        event_de: "WINDBÖEN",
        headline_de: "Amtliche WARNUNG vor WINDBÖEN",
        onset: now.toISOString(),
        expires: new Date(now.getTime() + 6 * 3600_000).toISOString(),
      },
    ],
  };
}

const HEADLINES = {
  main: [
    ["Testmeldung: Hauptnachricht des Tages mit einer Überschrift, die über zwei Zeilen läuft", "Beispielquelle", 0.6],
    ["Testmeldung: Zweite Nachricht mit Umlauten – Größe, Übersicht, Änderung", "Beispielquelle", 2.5],
    ["Testmeldung: Dritte Nachricht", "Beispielquelle", 5],
    ["Testmeldung: Eine sehr lange Überschrift, die zeigt, dass auch drei Zeilen und mehr sauber gekürzt werden, ohne dass etwas aus dem Kasten läuft oder die Zeile hart abgeschnitten wird", "Beispielquelle", 9],
    ["Testmeldung: Fünfte Nachricht von gestern", "Beispielquelle", 26],
    ["Testmeldung: Sechste Nachricht", "Beispielquelle", 50],
  ],
  side: [
    ["Testmeldung: Regionale Nachricht aus Kassel", "Beispielquelle", 1],
    ["Testmeldung: Verkehr in Nordhessen", "Beispielquelle", 3],
    ["Testmeldung: Veranstaltung am Wochenende", "Beispielquelle", 7],
    ["Testmeldung: Vierte regionale Nachricht", "Beispielquelle", 30],
  ],
};

function escapeXml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function rss(key, now) {
  const items = HEADLINES[key]
    .map(([title, source, hoursAgo]) => `
    <item>
      <title>${escapeXml(`${title} - ${source}`)}</title>
      <pubDate>${new Date(now.getTime() - hoursAgo * 3600_000).toUTCString()}</pubDate>
      <source url="https://example.org">${escapeXml(source)}</source>
    </item>`)
    .join("");
  return `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Test</title>${items}</channel></rss>`;
}

// A trading day from 9:00 to 17:30 Berlin time with a gentle upward drift, up to now.
function chart(now) {
  const open = berlinMidnight(now).getTime() + 9 * 3600_000;
  const close = open + 8.5 * 3600_000;
  const timestamp = [];
  const values = [];
  for (let t = open; t <= Math.min(now.getTime(), close); t += 300_000) {
    timestamp.push(Math.floor(t / 1000));
    values.push(Math.round((1830 + (t - open) / 600_000 + 6 * Math.sin((t - open) / 1_800_000)) * 100) / 100);
  }
  if (!values.length) {
    timestamp.push(Math.floor(open / 1000));
    values.push(1830);
  }
  return {
    chart: {
      result: [{
        meta: {
          currency: "EUR", symbol: "RHM.DE", fullExchangeName: "XETRA", longName: "Rheinmetall AG",
          regularMarketPrice: values.at(-1), chartPreviousClose: 1825.5, regularMarketTime: timestamp.at(-1),
          currentTradingPeriod: { regular: { start: Math.floor(open / 1000), end: Math.floor(close / 1000) } },
        },
        timestamp,
        indicators: { quote: [{ close: values }] },
      }],
      error: null,
    },
  };
}

const STOPS = [
  { type: "stop", id: "706070", name: "Kassel Rathaus" },
  { type: "station", id: "8000193", name: "Kassel Hbf" },
  { type: "stop", id: "706123", name: "Kassel Am Stern" },
];

function departures(now) {
  const at = (minutes) => new Date(now.getTime() + minutes * 60_000).toISOString();
  const line = (name, product) => ({ name, product });
  return {
    departures: [
      { when: at(2), plannedWhen: at(2), delay: 0, direction: "Wilhelmshöhe", line: line("1", "tram") },
      { when: at(6), plannedWhen: at(4), delay: 120, direction: "Kaufungen Papierfabrik", line: line("4", "tram") },
      { when: null, plannedWhen: at(9), delay: null, cancelled: true, direction: "Melsungen", line: line("RT5", "tram") },
      { when: at(15), plannedWhen: at(9), delay: 360, direction: "Kassel Brückenhof", line: line("16", "bus") },
      { when: at(18), plannedWhen: at(18), delay: 0, direction: "Ihringshäuser Straße", line: line("3", "tram") },
      { when: at(26), plannedWhen: at(26), delay: 0, direction: "Siegen Hbf", platform: "4", line: line("RE98", "regionalExpress") },
    ],
  };
}

const upstream = createServer((request, response) => {
  const url = new URL(request.url, "http://localhost");
  const now = new Date();
  const json = (payload) => {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify(payload));
  };
  if (url.pathname === "/current_weather") return json(current(now));
  if (url.pathname === "/weather") return json(forecast(now));
  if (url.pathname === "/alerts") return json(alerts(now));
  if (url.pathname.startsWith("/v8/finance/chart/")) return json(chart(now));
  if (url.pathname === "/locations") return json(STOPS.filter((stop) => stop.name.toLowerCase().includes((url.searchParams.get("query") ?? "").toLowerCase().split(" ")[0])));
  if (/^\/stops\/[^/]+\/departures$/.test(url.pathname)) return json(departures(now));
  if (url.pathname.startsWith("/rss/")) {
    response.writeHead(200, { "Content-Type": "application/rss+xml; charset=utf-8" });
    return response.end(rss(url.pathname.slice(5), now));
  }
  response.writeHead(404).end();
});

upstream.listen(0, "127.0.0.1", () => {
  const base = `http://127.0.0.1:${upstream.address().port}`;
  const dir = mkdtempSync(join(tmpdir(), "kiosk-e2e-"));
  const configPath = join(dir, "config.json");
  writeFileSync(configPath, JSON.stringify({
    port: KIOSK_PORT,
    adminHost: "127.0.0.1",
    adminPort: ADMIN_PORT,
    weather: { baseUrl: base },
    stock: { baseUrl: base },
    transit: { baseUrl: base },
    news: { main: { url: `${base}/rss/main` }, side: { url: `${base}/rss/side` } },
  }));
  // Update checks in e2e run a stand-in that reports "already current".
  const updateScript = join(dir, "update.sh");
  writeFileSync(updateScript, "#!/usr/bin/env bash\necho already current\nexit 10\n", { mode: 0o755 });
  const kiosk = spawn("python3", [
    "-m", "kiosk", "--config", configPath, "--cache-dir", join(dir, "cache"),
    "--state-dir", join(dir, "state"), "--data-dir", join(dir, "data"),
  ], {
    cwd: join(ROOT, "server"),
    stdio: "inherit",
    env: { ...process.env, NO_PROXY: "127.0.0.1,localhost", no_proxy: "127.0.0.1,localhost", KIOSK_UPDATE_SCRIPT: updateScript },
  });
  const stop = () => {
    kiosk.kill("SIGTERM");
    upstream.close();
    rmSync(dir, { recursive: true, force: true });
  };
  kiosk.on("exit", (code) => {
    stop();
    process.exit(code ?? 0);
  });
  for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => { stop(); process.exit(0); });
});
