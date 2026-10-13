import { expect, test } from "@playwright/test";

import { ADMIN, PASSWORD, PNG, SCREEN, clearUploads, collectConsole, getSettings, putSettings, signIn, upload } from "./helpers.js";

// The layout as the server starts it; every test restores it.
let defaults = null;

test.describe.configure({ mode: "serial" });

test.afterEach(async ({ page }) => {
  if (!defaults) return;
  await signIn(page);
  await putSettings(page.request, defaults);
  await clearUploads(page.request);
});

async function openAdmin(page, hash = "layout") {
  await signIn(page);
  await page.goto(`${ADMIN}/#${hash}`);
}

async function tile(page, id) {
  return page.locator(`.board-tile[data-widget="${id}"]`);
}

async function shrinkWeather(page) {
  // Two rows less for the weather column make room at the bottom right (5 x 2 cells).
  const weather = await tile(page, "weather");
  await weather.focus();
  await weather.press("Shift+ArrowUp");
  await expect(page.locator("#toasts")).toContainText("Größe von „Wetter“ geändert.");
  await weather.press("Shift+ArrowUp");
  await expect.poll(async () => (await getSettings(page.request)).settings.widgets.find((w) => w.id === "weather").h).toBe(6);
}

test("first setup with the code from the screen; the screen then hides the code", async ({ page, context }) => {
  const problems = collectConsole(page);
  const screen = await context.newPage();
  await screen.goto(SCREEN);
  const code = (await screen.locator(".overlay-code-value").textContent()).replace(/\s/g, "");
  expect(code).toMatch(/^\d{6}$/);
  await expect(screen.locator(".overlay-line")).toContainText(`:${new URL(ADMIN).port}`);

  await page.goto(ADMIN);
  await expect(page.getByRole("heading", { name: "Verwaltung einrichten" })).toBeVisible();
  await page.getByLabel("Code vom Bildschirm").fill("000000" === code ? "111111" : "000000");
  await page.getByLabel("Neues Passwort").fill(PASSWORD);
  await page.getByLabel("Passwort wiederholen").fill(PASSWORD);
  await page.getByRole("button", { name: "Einrichten" }).click();
  await expect(page.getByRole("alert")).toContainText("Der Code stimmt nicht");

  await page.getByLabel("Code vom Bildschirm").fill(`${code.slice(0, 3)} ${code.slice(3)}`);
  await page.getByLabel("Passwort wiederholen").fill("anders-anders");
  await page.getByRole("button", { name: "Einrichten" }).click();
  await expect(page.getByRole("alert")).toHaveText("Die beiden Passwörter sind nicht gleich.");

  await page.getByLabel("Passwort wiederholen").fill(PASSWORD);
  await page.getByRole("button", { name: "Einrichten" }).click();
  await expect(page.getByRole("heading", { name: "Layout" })).toBeVisible();
  await expect(screen.locator("#overlay"), "the screen hides the code within seconds").toBeHidden({ timeout: 10_000 });

  defaults = (await getSettings(page.request)).settings;
  expect(problems.filter((problem) => !problem.includes("401"))).toEqual([]);
});

test("sign out, a wrong password is refused, the right one signs in", async ({ page }) => {
  await openAdmin(page);
  await page.getByRole("button", { name: "Abmelden" }).click();
  await expect(page.getByRole("heading", { name: "Anmelden" })).toBeVisible();
  await page.getByLabel("Passwort").fill("falsch-falsch");
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByRole("alert")).toHaveText("Das Passwort stimmt nicht.");
  await page.getByLabel("Passwort").fill(PASSWORD);
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByRole("link", { name: "Layout" })).toHaveAttribute("aria-current", "page");
});

test("keyboard: resize, move, and delete starts on Cancel", async ({ page }) => {
  await openAdmin(page);
  await shrinkWeather(page);
  const weather = await tile(page, "weather");
  await weather.focus();
  await weather.press("ArrowDown");
  await expect.poll(async () => (await getSettings(page.request)).settings.widgets.find((w) => w.id === "weather").y).toBe(1);
  await expect(page.locator("#announce")).toHaveText("Wetter: Spalte 8, Zeile 2, 5 × 6 Felder");

  await weather.press("ArrowLeft");
  await expect(page.locator("#announce")).toHaveText("Dort ist kein Platz.");

  await weather.press("Delete");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("„Wetter“ entfernen?");
  await expect(dialog.getByRole("button", { name: "Abbrechen" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  expect((await getSettings(page.request)).settings.widgets.some((w) => w.id === "weather")).toBe(true);
});

test("dragging the corner resizes a tile, and undo restores it", async ({ page }) => {
  await openAdmin(page);
  const board = page.locator(".board");
  const weather = await tile(page, "weather");
  const box = await board.boundingBox();
  const handle = weather.locator(".board-handle");
  const start = await handle.boundingBox();
  const rowHeight = box.height / 8;
  await page.mouse.move(start.x + start.width / 2, start.y + start.height / 2);
  await page.mouse.down();
  await page.mouse.move(start.x + start.width / 2, start.y - rowHeight * 2, { steps: 8 });
  await page.mouse.up();
  await expect.poll(async () => (await getSettings(page.request)).settings.widgets.find((w) => w.id === "weather").h).toBe(6);

  await page.locator("#toasts").getByRole("button", { name: "Rückgängig" }).click();
  await expect.poll(async () => (await getSettings(page.request)).settings.widgets.find((w) => w.id === "weather").h).toBe(8);
});

test("a new message tile shows up on the screen within seconds", async ({ page, context }) => {
  await openAdmin(page);
  const screen = await context.newPage();
  await screen.goto(SCREEN);
  await shrinkWeather(page);

  await page.getByRole("button", { name: "Mitteilung hinzufügen" }).click();
  await expect(page.locator(".inspector")).toContainText("Mitteilung");
  const title = page.locator(".inspector").getByLabel("Überschrift");
  await title.fill("Willkommen, Firma Test");
  await title.press("Tab");
  await expect(screen.locator(".tile-message .message-title")).toHaveText("Willkommen, Firma Test", { timeout: 10_000 });

  await page.locator(".inspector").getByLabel("Farbig hinterlegen").check();
  await expect(screen.locator(".tile-message")).toHaveClass(/message-highlight/, { timeout: 10_000 });
});

test("departures: search a stop, pick it, the screen shows its departures", async ({ page, context }) => {
  await openAdmin(page);
  const screen = await context.newPage();
  await screen.goto(SCREEN);
  await shrinkWeather(page);
  await page.getByRole("button", { name: "Abfahrten hinzufügen" }).click();
  const inspector = page.locator(".inspector");
  await expect(inspector.getByText("Noch keine Haltestelle gewählt.")).toBeVisible();
  await expect(screen.locator(".tile-transit .placeholder")).toContainText("Noch keine Haltestelle gewählt", { timeout: 10_000 });

  await inspector.getByRole("searchbox", { name: "Haltestelle suchen" }).fill("Kassel Rat");
  await inspector.getByRole("button", { name: "Kassel Rathaus" }).click();
  await expect(inspector.locator(".stop-current")).toHaveText("Kassel Rathaus");
  await expect(screen.locator(".tile-transit .panel-title")).toHaveText("Kassel Rathaus", { timeout: 10_000 });
  await expect(screen.locator(".tile-transit .departure").first()).toBeVisible({ timeout: 10_000 });

  await inspector.getByLabel("Bus").uncheck();
  await expect.poll(async () => (await getSettings(page.request)).settings.widgets.find((w) => w.type === "transit").options.products)
    .not.toContain("bus");
});

test("night: the monitor can be switched off, and TVs over HDMI-CEC", async ({ page }) => {
  await openAdmin(page, "settings");
  await expect(page.getByLabel("Monitor ausschalten statt nur schwarz")).toBeDisabled();
  await page.getByLabel("Nachts abschalten").check();
  await expect(page.getByLabel("Monitor ausschalten statt nur schwarz")).toBeEnabled();
  await page.getByLabel("Fernseher über HDMI-CEC ein- und ausschalten").check();
  await expect.poll(async () => (await getSettings(page.request)).settings.display.sleep)
    .toMatchObject({ enabled: true, powerOff: true, cec: true });
  const display = await (await page.request.get(`${SCREEN}/api/display`)).json();
  expect(display).toMatchObject({ powerOff: true, cec: true });
});

test("updates: switch off, set the time, check now", async ({ page }) => {
  await openAdmin(page, "device");
  await expect(page.getByText("Noch nicht gesucht.")).toBeVisible();
  await page.getByLabel("Um").fill("04:20");
  await page.getByLabel("Um").dispatchEvent("change");
  await expect.poll(async () => (await getSettings(page.request)).settings.updates.time).toBe("04:20");
  await page.getByRole("button", { name: "Jetzt nach Updates suchen" }).click();
  await expect(page.getByText(/^Zuletzt gerade eben: Bereits aktuell\.$/)).toBeVisible({ timeout: 15_000 });
  await page.getByLabel("Automatisch aktualisieren").uncheck();
  await expect.poll(async () => (await getSettings(page.request)).settings.updates.enabled).toBe(false);
});

test("a feed URL that is not http(s) is refused at the field", async ({ page }) => {
  await openAdmin(page);
  await (await tile(page, "news-main")).click();
  const url = page.locator(".inspector").getByLabel("Feed-Adresse (RSS oder Atom)");
  await url.fill("javascript:alert(1)");
  await url.press("Tab");
  await expect(page.locator("#toasts")).toContainText("http:// oder https://");
  expect((await getSettings(page.request)).settings.widgets.find((w) => w.id === "news-main").options.url).toMatch(/^https?:\/\/127\.0\.0\.1/);
});

test("logo: upload, use, place as a tile, shown on the screen; an image in use cannot be deleted", async ({ page, context }) => {
  await openAdmin(page);
  await shrinkWeather(page);
  await page.getByRole("link", { name: "Logo und Bilder" }).click();
  await page.locator("#upload-input").setInputFiles({ name: "Firmenlogo.png", mimeType: "image/png", buffer: PNG });
  await expect(page.locator("#toasts")).toContainText("Bild hochgeladen.");
  await page.getByRole("button", { name: "Als Logo verwenden" }).click();
  await expect(page.locator(".logo-current img")).toBeVisible();
  await page.getByRole("button", { name: "Logo-Kachel hinzufügen" }).click();
  await expect(page.locator("#toasts")).toContainText("„Logo“ hinzugefügt.");

  const screen = await context.newPage();
  await screen.goto(SCREEN);
  const logo = screen.locator(".tile-logo .logo-image");
  await expect(logo).toBeVisible();
  await expect.poll(() => logo.evaluate((img) => img.naturalWidth)).toBe(8);

  await page.getByRole("button", { name: "Firmenlogo.png Löschen" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Löschen" }).click();
  await expect(page.locator("#toasts")).toContainText("wird noch verwendet");
});

test("a template replaces the layout and keeps the feeds; the dialog can be cancelled", async ({ page, context }) => {
  await openAdmin(page);
  const apply = page.getByRole("button", { name: "Vorlage „Werk und Produktion“ anwenden…" });
  await apply.click();
  await page.getByRole("dialog").getByRole("button", { name: "Abbrechen" }).click();
  await expect(apply).toBeFocused();
  expect((await getSettings(page.request)).settings.widgets.length).toBe(4);

  await apply.click();
  await page.getByRole("dialog").getByRole("button", { name: "Anwenden" }).click();
  await expect(page.locator("#toasts")).toContainText("Vorlage „Werk und Produktion“ angewendet.");
  const screen = await context.newPage();
  await screen.goto(SCREEN);
  await expect(screen.locator(".tile-counter .big-label")).toContainText("Tage ohne Arbeitsunfall");
  await expect(screen.locator(".tile-countdown .big-number")).toHaveText(/^\d+$/);
  await expect(screen.locator(".tile-news .panel-title")).toHaveText("Rheinmetall");
});

test("settings: a place from the list moves the weather; the scale applies at once", async ({ page, context }) => {
  await openAdmin(page, "settings");
  const screen = await context.newPage();
  await screen.goto(SCREEN);
  await page.getByLabel("Ort übernehmen").selectOption("Düsseldorf");
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("Düsseldorf");
  await expect(screen.locator(".tile-weather .panel-title")).toHaveText("Wetter in Düsseldorf", { timeout: 15_000 });

  const before = await screen.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
  await page.getByLabel("Schriftgröße").fill("120");
  await page.getByLabel("Schriftgröße").dispatchEvent("change");
  await expect.poll(() => screen.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize)), { timeout: 10_000 })
    .toBeCloseTo(before * 1.2, 1);
});

test("night mode blanks the screen", async ({ page, context }) => {
  await signIn(page);
  const { settings } = await getSettings(page.request);
  settings.display.sleep = { enabled: true, from: "00:00", to: "23:59", weekends: true };
  await putSettings(page.request, settings);
  const screen = await context.newPage();
  await screen.goto(SCREEN);
  await expect(screen.locator("body")).toHaveClass(/asleep/);
  await expect(screen.locator(".screen")).toBeHidden();
});

test("device page: screen size, data sources, reload the screen", async ({ page, context }) => {
  const screen = await context.newPage();
  await screen.setViewportSize({ width: 1600, height: 900 });
  await screen.goto(SCREEN);
  await openAdmin(page, "device");
  await expect(page.getByText(/Verbunden, 1600 × 900 Pixel/)).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".source").first()).toContainText("Wetter für Kassel");
  await expect(page.locator(".source").first()).toContainText("Aktualisiert");

  await screen.evaluate(() => { window.kioskMarker = true; });
  await page.getByRole("button", { name: "Bildschirm neu laden" }).click();
  await expect.poll(() => screen.evaluate(() => window.kioskMarker === undefined), { timeout: 10_000 }).toBe(true);
});

test("changing the password keeps this session and signs others out", async ({ page, browser }) => {
  await openAdmin(page, "device");
  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await signIn(otherPage);

  await page.getByLabel("Bisheriges Passwort").fill(PASSWORD);
  await page.getByLabel("Neues Passwort").fill("neues-e2e-passwort");
  await page.getByRole("button", { name: "Passwort ändern" }).click();
  await expect(page.locator("#toasts")).toContainText("Passwort geändert.");
  expect((await otherPage.request.get(`${ADMIN}/api/admin/settings`)).status()).toBe(401);

  // Back to the known password for the other tests.
  await page.getByLabel("Bisheriges Passwort").fill("neues-e2e-passwort");
  await page.getByLabel("Neues Passwort").fill(PASSWORD);
  await page.getByRole("button", { name: "Passwort ändern" }).click();
  await expect(page.locator("#toasts")).toContainText("Passwort geändert.");
  await other.close();
});

for (const width of [360, 390, 768, 1280, 1920]) {
  test(`every admin page fits ${width} px without horizontal scrolling or console errors`, async ({ page }) => {
    const problems = collectConsole(page);
    await page.setViewportSize({ width, height: 900 });
    for (const hash of ["layout", "media", "settings", "device"]) {
      await openAdmin(page, hash);
      await expect(page.locator(".page-title").first()).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      expect(overflow, `#${hash} scrolls sideways`).toBeLessThanOrEqual(0);
    }
    expect(problems).toEqual([]);
  });
}

test("selected and current states are a neutral tint, never a colored frame", async ({ page }) => {
  await openAdmin(page);
  await (await tile(page, "clock")).click();
  const frames = await page.evaluate(() => {
    const neutral = new Set();
    for (const token of ["--border", "--input-border", "--focus-ring"]) {
      const probe = document.createElement("span");
      probe.style.color = getComputedStyle(document.documentElement).getPropertyValue(token);
      document.body.append(probe);
      neutral.add(getComputedStyle(probe).color);
      probe.remove();
    }
    const offenders = [];
    for (const element of document.querySelectorAll(".board-tile.is-selected, .nav-link[aria-current], .segment[aria-pressed=true]")) {
      const style = getComputedStyle(element);
      for (const side of ["Top", "Right", "Bottom", "Left"]) {
        const width = parseFloat(style[`border${side}Width`]);
        const color = style[`border${side}Color`];
        if (width > 0 && !neutral.has(color) && color !== "rgba(0, 0, 0, 0)") offenders.push(`${element.className}: ${color}`);
      }
      if (style.boxShadow !== "none") offenders.push(`${element.className}: box-shadow`);
    }
    return offenders;
  });
  expect(frames).toEqual([]);
});
