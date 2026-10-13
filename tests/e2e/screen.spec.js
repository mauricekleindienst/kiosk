import { expect, test } from "@playwright/test";

import { clearUploads, collectConsole, ensureAdmin, getSettings, putSettings, signIn, upload } from "./helpers.js";

const SIZES = [
  { name: "720p", width: 1280, height: 720 },
  { name: "1080p", width: 1920, height: 1080 },
  { name: "1440p", width: 2560, height: 1440 },
  { name: "4K", width: 3840, height: 2160 },
  { name: "ultrawide", width: 2560, height: 1080 },
  { name: "portrait", width: 1080, height: 1920 },
];

let defaults = null;

test.beforeAll(async ({ request }) => {
  await ensureAdmin(request);
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
  defaults ??= (await getSettings(page.request)).settings;
});

test.afterEach(async ({ page }) => {
  await signIn(page);
  await putSettings(page.request, defaults);
  await clearUploads(page.request);
});

async function loaded(page) {
  await page.goto("/");
  await expect(page.locator(".tile").first(), "the tiles are built").toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

async function layoutReport(page) {
  return page.evaluate(() => {
    // Inside the tile's content box: running into the padding counts as cut.
    const inside = (child, tile) => {
      const box = tile.getBoundingClientRect();
      const style = getComputedStyle(tile);
      const item = child.getBoundingClientRect();
      const bare = tile.classList.contains("tile-slideshow");
      return item.bottom <= box.bottom - (bare ? 0 : parseFloat(style.paddingBottom)) + 1
        && item.right <= box.right - (bare ? 0 : parseFloat(style.paddingRight)) + 1;
    };
    return {
      scroll: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
      viewport: [innerWidth, innerHeight],
      tilesInside: [...document.querySelectorAll(".tile")].every((tile) => {
        const box = tile.getBoundingClientRect();
        return box.left >= 0 && box.top >= 0 && box.right <= innerWidth + 0.5 && box.bottom <= innerHeight + 0.5;
      }),
      cut: [...document.querySelectorAll(".tile")].flatMap((tile) =>
        [...tile.querySelectorAll(".headline, .day, .zone, .big-number, .big-label, .message-title, .clock-time, .clock-date, .now, .calendar-day, .stock-price, .stock-change, .departure")]
          .filter((item) => item.offsetParent !== null && !inside(item, tile))
          .map((item) => `${tile.dataset.widget}: ${item.className} "${item.textContent.slice(0, 40)}"`)),
      clockSize: parseFloat(getComputedStyle(document.querySelector(".clock-time") ?? document.body).fontSize),
      // Readable from a few metres: no visible text below 0.6 % of the size the layout scales with
      // (the longer side in portrait, the 16:9 area in landscape, as in screen.css).
      tinyText: [...document.querySelectorAll(".tile *")]
        .filter((node) => node.offsetParent !== null && [...node.childNodes].some((child) => child.nodeType === 3 && child.textContent.trim()))
        .filter((node) => parseFloat(getComputedStyle(node).fontSize)
          < (innerHeight > innerWidth ? innerHeight : Math.min(innerWidth, innerHeight * 16 / 9)) * 0.006)
        .map((node) => `${node.closest(".tile").dataset.widget}: ${node.className} ${getComputedStyle(node).fontSize}`),
    };
  });
}

test("shows time, date, weather and news without console errors", async ({ page }) => {
  const problems = collectConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await loaded(page);

  await expect(page.locator(".clock-time")).toHaveText(/^\d{2}:\d{2}$/);
  await expect(page.locator(".clock-date")).toHaveText(/^(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag), \d{1,2}\. \S+ \d{4}$/);
  await expect(page.locator(".clock-meta")).toHaveText(/^KW \d{1,2} · /);
  await expect(page.locator(".tile-weather .panel-title")).toHaveText("Wetter in Kassel");
  await expect(page.locator(".now-temperature")).toHaveText("12°");
  await expect(page.locator(".alert-headline")).toContainText("Amtliche WARNUNG vor WINDBÖEN");
  await expect(page.locator(".tile-weather .source-note")).toHaveText("Quelle: Deutscher Wetterdienst");
  const main = page.locator('[data-widget="news-main"]');
  await expect(main.locator(".panel-title")).toHaveText("Rheinmetall");
  await expect(main.locator(".headline-title").first()).toHaveText(/^Testmeldung: Hauptnachricht/);
  await expect(main.locator(".headline-meta").first()).toHaveText(/^Beispielquelle · vor 3\d Min\.$/);
  await expect(page.locator('[data-widget="news-side"] .headline')).toHaveCount(2);
  await expect(page.locator(".status:visible")).toHaveCount(0);
  await expect(page.locator("#overlay")).toBeHidden();
  expect(problems).toEqual([]);
});

for (const size of SIZES) {
  test(`fills a ${size.name} screen without overflow or cut-off content`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await loaded(page);
    await expect(page.locator(".day").first()).toBeVisible();
    const report = await layoutReport(page);
    expect(report.scroll, "no scrolling in either direction").toEqual(report.viewport);
    expect(report.tilesInside, "every tile inside the screen").toBe(true);
    expect(report.cut, "nothing cut in half").toEqual([]);
    expect(report.tinyText, "no tiny text").toEqual([]);
    expect(await page.locator('[data-widget="news-main"] .headline').count(), "lead plus at least one more").toBeGreaterThanOrEqual(2);
    expect(await page.locator(".day").count(), "at least three forecast days").toBeGreaterThanOrEqual(3);
    // Readable from across the office: the clock at least 7 % of the screen height in landscape.
    if (size.width > size.height) expect(report.clockSize / size.height).toBeGreaterThan(0.07);
    await testInfo.attach(`screen-${size.name}`, { body: await page.screenshot(), contentType: "image/png" });
  });
}

test("every widget type at every size: nothing overflows, nothing is cut", async ({ page }, testInfo) => {
  const image = await upload(page.request, "bild.png");
  const settings = structuredClone(defaults);
  settings.logo = image.id;
  settings.widgets = [
    { id: "clock", type: "clock", x: 0, y: 0, w: 3, h: 2, options: { style: "analog", showSeconds: true, showLogo: true } },
    { id: "clock-2", type: "clock", x: 3, y: 0, w: 4, h: 1, options: { showSeconds: true } },
    { id: "logo", type: "logo", x: 3, y: 1, w: 2, h: 1, options: {} },
    { id: "counter", type: "counter", x: 5, y: 1, w: 2, h: 1, options: { since: "2026-01-05" } },
    { id: "weather", type: "weather", x: 7, y: 0, w: 5, h: 4, options: {} },
    { id: "news", type: "news", x: 0, y: 2, w: 4, h: 3, options: { title: "Rheinmetall", url: defaults.widgets[1].options.url } },
    { id: "calendar", type: "calendar", x: 4, y: 2, w: 3, h: 3, options: {} },
    { id: "stock", type: "stock", x: 7, y: 4, w: 3, h: 2, options: {} },
    { id: "countdown", type: "countdown", x: 10, y: 4, w: 2, h: 1, options: { label: "Sommerfest", date: "2027-07-02" } },
    { id: "worldclock", type: "worldclock", x: 10, y: 5, w: 2, h: 3, options: {} },
    { id: "transit", type: "transit", x: 0, y: 5, w: 4, h: 3, options: { stop: { id: "706070", name: "Kassel Rathaus" } } },
    { id: "message", type: "message", x: 4, y: 5, w: 3, h: 3, options: {
      title: "Herzlich willkommen, liebe Gäste aus Unterlüß", body: "Besprechung im Raum „Fulda“ ab 10 Uhr.\nKaffee steht bereit.", size: "large", highlight: true,
    } },
    { id: "slideshow", type: "slideshow", x: 7, y: 6, w: 3, h: 2, options: { images: [image.id], seconds: 5 } },
  ];
  await putSettings(page.request, settings);

  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await loaded(page);
    await expect(page.locator(".tile")).toHaveCount(settings.widgets.length);
    await expect(page.locator(".tile-weather .now-temperature")).toBeVisible();
    await expect(page.locator(".tile-calendar .calendar-today")).toHaveCount(1);
    await expect(page.locator(".tile-countdown .big-number")).toHaveText(/^\d+$/);
    await expect(page.locator(".tile-counter .big-label")).toContainText("Tage ohne Arbeitsunfall");
    await expect(page.locator(".tile-stock .stock-price")).toHaveText(/^1\.8\d\d,\d\d\s€$/);
    await expect(page.locator(".tile-transit .departure").first()).toBeVisible();
    await expect.poll(() => page.locator(".tile-logo .logo-image").evaluate((img) => img.naturalWidth)).toBe(8);
    const report = await layoutReport(page);
    expect(report.scroll, `${size.name}: no scrolling`).toEqual(report.viewport);
    expect(report.tilesInside, `${size.name}: tiles inside`).toBe(true);
    expect(report.cut, `${size.name}: nothing cut`).toEqual([]);
    expect(report.tinyText, `${size.name}: no tiny text`).toEqual([]);
    await testInfo.attach(`all-widgets-${size.name}`, { body: await page.screenshot(), contentType: "image/png" });
  }
});

test("the analog clock shows the time", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-10-13T08:15:30Z"));
  const settings = structuredClone(defaults);
  settings.widgets[0].options.style = "analog";
  await putSettings(page.request, settings);
  await loaded(page);
  const angles = await page.evaluate(() => Object.fromEntries(["hour", "minute"].map((hand) => [hand,
    Number(document.querySelector(`.analog-${hand}`).getAttribute("transform").match(/rotate\(([\d.]+)/)[1])])));
  // 10:15:30 in Berlin: the minute hand at 15.5 minutes, the hour hand just past the 10.
  expect(angles.minute).toBeCloseTo(93, 0);
  expect(angles.hour).toBeCloseTo(307.75, 1);
});

test("stock tile: price, change against yesterday and the day's curve", async ({ page }) => {
  const settings = structuredClone(defaults);
  settings.widgets[0].w = 4;
  settings.widgets.push({ id: "stock", type: "stock", x: 4, y: 0, w: 3, h: 2, options: {} });
  await putSettings(page.request, settings);
  await loaded(page);
  const tile = page.locator(".tile-stock");
  await expect(tile.locator(".panel-title")).toHaveText("Rheinmetall");
  await expect(tile.locator(".stock-change")).toHaveText(/^[+\u2212][\d.,]+\s€ \([+\u2212][\d,]+\u202f%\)$/);
  await expect(tile.locator(".stock-meta")).toContainText("XETRA · Stand");
  expect(await tile.locator(".stock-line").getAttribute("points")).toMatch(/^[\d.]+,[\d.]+( [\d.]+,[\d.]+)+$/);
  await expect(tile.locator(".stock-baseline")).toHaveCount(1);
});

test("departures: soonest first, delays and cancellations, walking time hides what is out of reach", async ({ page }) => {
  const settings = structuredClone(defaults);
  settings.widgets[3].h = 4;
  settings.widgets.push({ id: "transit", type: "transit", x: 7, y: 4, w: 5, h: 4, options: { stop: { id: "706070", name: "Kassel Rathaus" } } });
  await putSettings(page.request, settings);
  await loaded(page);
  const tile = page.locator(".tile-transit");
  await expect(tile.locator(".panel-title")).toHaveText("Kassel Rathaus");
  await expect(tile.locator(".departure-line").first()).toHaveText("1");
  await expect(tile.locator(".departure").nth(1).locator(".departure-delay")).toHaveText("+2");
  await expect(tile.locator(".departure-cancelled .departure-state")).toHaveText("fällt aus");
  await expect(tile.locator(".departure").nth(3).locator(".departure-delay")).toHaveClass(/departure-delay-late/);

  settings.widgets.at(-1).options.walkMinutes = 5;
  await putSettings(page.request, settings);
  await expect(tile.locator(".departure-line").first()).toHaveText("4", { timeout: 10_000 });
});

test("feed text is shown as text, never as markup", async ({ page }) => {
  await page.route("**/api/state", async (route) => {
    const response = await route.fetch();
    const state = await response.json();
    state.widgets["news-main"].data[0].title = '<img src=x onerror="document.title=1">Übernahme & Co.';
    await route.fulfill({ response, json: state });
  });
  await loaded(page);
  const title = page.locator('[data-widget="news-main"] .headline-title').first();
  await expect(title).toHaveText('<img src=x onerror="document.title=1">Übernahme & Co.');
  await expect(page.locator('[data-widget="news-main"] img')).toHaveCount(0);
});

test("when the data server is gone, the last data stays with a quiet notice", async ({ page }) => {
  await page.clock.install();
  await loaded(page);
  await expect(page.locator(".status:visible")).toHaveCount(0);

  await page.route("**/api/**", (route) => route.abort());
  await page.clock.runFor(4_000);
  await expect(page.locator(".tile-weather .status")).toBeVisible();
  await expect(page.locator(".tile-weather .status")).toHaveText(/^Keine Verbindung – Stand \d{2}:\d{2} Uhr$/);
  await expect(page.locator('[data-widget="news-main"] .status')).toBeVisible();
  await expect(page.locator(".now-temperature"), "the last weather stays").toHaveText("12°");

  await page.unroute("**/api/**");
  await page.clock.runFor(4_000);
  await expect(page.locator(".status:visible")).toHaveCount(0);
});

test("an unreachable weather service on first start explains itself", async ({ page }) => {
  await page.route("**/api/state", async (route) => {
    const response = await route.fetch();
    const state = await response.json();
    state.weather = { data: null, fetchedAt: null, error: "api.brightsky.dev is not reachable", refreshMinutes: 10 };
    state.widgets["news-side"] = { ...state.widgets["news-side"], data: [] };
    await route.fulfill({ response, json: state });
  });
  await loaded(page);
  await expect(page.locator(".tile-weather .panel-body")).toHaveText("Wetterdaten sind gerade nicht verfügbar. Der Bildschirm versucht es jede Minute erneut.");
  await expect(page.locator('[data-widget="news-side"] .panel-body')).toHaveText("Keine aktuellen Meldungen.");
});

test("the setup notice shows the code and the address, nothing else covers the screen", async ({ page }) => {
  await page.route("**/api/state", async (route) => {
    const response = await route.fetch();
    const state = await response.json();
    state.setup = { code: "123456", urls: ["http://192.168.1.50:8081", "http://kiosk.local:8081"] };
    await route.fulfill({ response, json: state });
  });
  await loaded(page);
  await expect(page.locator(".overlay-code-value")).toHaveText("123 456");
  await expect(page.locator(".overlay-line")).toHaveText("Im Firmennetz öffnen: http://192.168.1.50:8081 oder http://kiosk.local:8081");
});

test("no tile draws a colored frame", async ({ page }) => {
  await loaded(page);
  const framed = await page.evaluate(() => {
    const probe = document.createElement("span");
    probe.style.color = getComputedStyle(document.documentElement).getPropertyValue("--border");
    document.body.append(probe);
    const allowed = new Set([getComputedStyle(probe).color, "rgba(0, 0, 0, 0)"]);
    probe.remove();
    const offenders = [];
    for (const element of document.querySelectorAll("body *")) {
      const style = getComputedStyle(element);
      for (const side of ["Top", "Right", "Bottom", "Left"]) {
        if (parseFloat(style[`border${side}Width`]) > 0 && !allowed.has(style[`border${side}Color`])) {
          offenders.push(`${element.className}: border-${side.toLowerCase()} ${style[`border${side}Color`]}`);
        }
      }
      if (style.boxShadow !== "none") offenders.push(`${element.className}: box-shadow`);
    }
    return offenders;
  });
  expect(framed).toEqual([]);
});
