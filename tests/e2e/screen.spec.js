import { expect, test } from "@playwright/test";

const SIZES = [
  { name: "720p", width: 1280, height: 720 },
  { name: "1080p", width: 1920, height: 1080 },
  { name: "1440p", width: 2560, height: 1440 },
  { name: "4K", width: 3840, height: 2160 },
  { name: "ultrawide", width: 2560, height: 1080 },
  { name: "portrait", width: 1080, height: 1920 },
];

function collectConsole(page) {
  const problems = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) problems.push(`${message.type()}: ${message.text()}`);
  });
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  return problems;
}

async function loaded(page) {
  await page.goto("/");
  await expect(page.locator(".day").first(), "the forecast rendered").toBeVisible();
  await expect(page.locator("#news-main-body .headline").first(), "the main news rendered").toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

test("shows time, date, weather and news without console errors", async ({ page }) => {
  const problems = collectConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await loaded(page);

  await expect(page.locator("#clock")).toHaveText(/^\d{2}:\d{2}$/);
  await expect(page.locator("#date")).toHaveText(/^(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag), \d{1,2}\. \S+ \d{4}$/);
  await expect(page.locator("#date-meta")).toHaveText(/^KW \d{1,2} · /);
  await expect(page.locator("#weather-title")).toHaveText("Wetter in Kassel");
  await expect(page.locator(".now-temperature")).toHaveText("12°");
  await expect(page.locator(".alert-headline")).toContainText("Amtliche WARNUNG vor WINDBÖEN");
  await expect(page.locator(".hour")).toHaveCount(12);
  await expect(page.locator("#news-main-title")).toHaveText("Rheinmetall");
  await expect(page.locator("#news-main-body .headline-title").first()).toHaveText(/^Testmeldung: Hauptnachricht/);
  await expect(page.locator("#news-main-body .headline-meta").first()).toHaveText(/^Beispielquelle · vor 3\d Min\.$/);
  await expect(page.locator("#weather-source")).toHaveText("Quelle: Deutscher Wetterdienst");
  await expect(page.locator(".status:visible")).toHaveCount(0);
  expect(problems).toEqual([]);
});

for (const size of SIZES) {
  test(`fills a ${size.name} screen without overflow or cut-off content`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await loaded(page);

    const layout = await page.evaluate(() => {
      const fits = (child, box) => child.getBoundingClientRect().bottom <= box.getBoundingClientRect().bottom + 1;
      return {
        scroll: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
        viewport: [innerWidth, innerHeight],
        panelsInside: [...document.querySelectorAll(".panel")].every((panel) => {
          const box = panel.getBoundingClientRect();
          return box.left >= 0 && box.top >= 0 && box.right <= innerWidth + 0.5 && box.bottom <= innerHeight + 0.5;
        }),
        cutHeadlines: [...document.querySelectorAll(".panel-news .panel-body")].flatMap((body) =>
          [...body.querySelectorAll(".headline")].filter((item) => !fits(item, body)).map((item) => item.textContent)),
        cutDays: [...document.querySelectorAll(".day")].filter((day) => !fits(day, document.getElementById("weather-body"))).length,
        days: document.querySelectorAll(".day").length,
        mainHeadlines: document.querySelectorAll("#news-main-body .headline").length,
        sideHeadlines: document.querySelectorAll("#news-side-body .headline").length,
        clockSize: parseFloat(getComputedStyle(document.getElementById("clock")).fontSize),
      };
    });

    expect(layout.scroll, "no scrolling in either direction").toEqual(layout.viewport);
    expect(layout.panelsInside, "every panel inside the screen").toBe(true);
    expect(layout.cutHeadlines, "no headline cut in half").toEqual([]);
    expect(layout.cutDays, "no forecast day cut in half").toBe(0);
    expect(layout.days, "at least five days of forecast").toBeGreaterThanOrEqual(5);
    expect(layout.mainHeadlines, "lead plus at least one more headline").toBeGreaterThanOrEqual(2);
    expect(layout.sideHeadlines).toBeGreaterThanOrEqual(1);
    // Readable from across the office: the clock at least 7 % of the screen height in landscape.
    if (size.width > size.height) expect(layout.clockSize / size.height).toBeGreaterThan(0.07);

    await testInfo.attach(`screen-${size.name}`, { body: await page.screenshot(), contentType: "image/png" });
  });
}

test("states, hover and focus never draw colored frames", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await loaded(page);
  const framed = await page.evaluate(() => {
    const neutral = getComputedStyle(document.documentElement).getPropertyValue("--border").trim();
    const toRgb = (color) => {
      const probe = document.createElement("span");
      probe.style.color = color;
      document.body.append(probe);
      const rgb = getComputedStyle(probe).color;
      probe.remove();
      return rgb;
    };
    const allowed = new Set([toRgb(neutral)]);
    const offenders = [];
    for (const element of document.querySelectorAll("body *")) {
      const style = getComputedStyle(element);
      for (const side of ["Top", "Right", "Bottom", "Left"]) {
        if (parseFloat(style[`border${side}Width`]) > 0 && !allowed.has(style[`border${side}Color`])) {
          offenders.push(`${element.className}: border-${side.toLowerCase()} ${style[`border${side}Color`]}`);
        }
      }
      if (style.boxShadow !== "none") offenders.push(`${element.className}: box-shadow ${style.boxShadow}`);
      if (style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0) offenders.push(`${element.className}: outline`);
    }
    return offenders;
  });
  expect(framed).toEqual([]);
});

test("feed text is shown as text, never as markup", async ({ page }) => {
  await page.route("/api/state", async (route) => {
    const response = await route.fetch();
    const state = await response.json();
    state.news.main.data[0].title = '<img src=x onerror="document.title=1">Übernahme & Co.';
    await route.fulfill({ response, json: state });
  });
  await loaded(page);
  await expect(page.locator("#news-main-body .headline-title").first()).toHaveText('<img src=x onerror="document.title=1">Übernahme & Co.');
  await expect(page.locator("#news-main-body img")).toHaveCount(0);
});

test("when the data server is gone, the last data stays with a quiet notice", async ({ page }) => {
  await page.clock.install();
  await loaded(page);
  await expect(page.locator(".status:visible")).toHaveCount(0);

  await page.route("/api/state", (route) => route.abort());
  await page.clock.runFor(61_000);

  await expect(page.locator("#weather-status")).toBeVisible();
  await expect(page.locator("#weather-status")).toHaveText(/^Keine Verbindung – Stand \d{2}:\d{2} Uhr$/);
  await expect(page.locator("#news-main-status")).toBeVisible();
  await expect(page.locator(".now-temperature"), "the last weather stays").toHaveText("12°");

  await page.unroute("/api/state");
  await page.clock.runFor(61_000);
  await expect(page.locator(".status:visible")).toHaveCount(0);
});

test("before any data arrives, every block says it is loading", async ({ page }) => {
  await page.route("/api/state", (route) => route.abort());
  await page.goto("/");
  await expect(page.locator("#clock")).toHaveText(/^\d{2}:\d{2}$/);
  await expect(page.locator("#date")).not.toBeEmpty();
  await expect(page.locator("#weather-body")).toHaveText("Wetterdaten werden geladen…");
  await expect(page.locator("#news-main-body")).toHaveText("Nachrichten werden geladen…");
  await expect(page.locator("#news-side-body")).toHaveText("Nachrichten werden geladen…");
  await expect(page.locator(".status:visible"), "nothing is stale before anything arrived").toHaveCount(0);
});

test("an unreachable weather service on first start explains itself", async ({ page }) => {
  await page.route("/api/state", async (route) => {
    const response = await route.fetch();
    const state = await response.json();
    state.weather = { data: null, fetchedAt: null, error: "api.brightsky.dev is not reachable", refreshMinutes: 10 };
    state.news.side = { ...state.news.side, data: [] };
    await route.fulfill({ response, json: state });
  });
  await page.goto("/");
  await expect(page.locator("#weather-body")).toHaveText("Wetterdaten sind gerade nicht verfügbar. Der Bildschirm versucht es jede Minute erneut.");
  await expect(page.locator("#news-side-body")).toHaveText("Keine aktuellen Meldungen.");
});
