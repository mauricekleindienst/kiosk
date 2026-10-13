import { expect } from "@playwright/test";

export const SCREEN = `http://127.0.0.1:${process.env.KIOSK_E2E_PORT ?? 8199}`;
export const ADMIN = `http://127.0.0.1:${process.env.KIOSK_E2E_ADMIN_PORT ?? 8198}`;
export const PASSWORD = "e2e-passwort";
// An 8 x 4 red PNG, small enough to inline.
export const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAECAYAAACzzX7wAAAAEklEQVR4nGM4IafxHx9moL0CAOHEQaEL9VCrAAAAAElFTkSuQmCC", "base64");

export function collectConsole(page) {
  const problems = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) problems.push(`${message.type()}: ${message.text()}`);
  });
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  return problems;
}

/** Makes sure an admin password exists (set up with the code the screen shows). */
export async function ensureAdmin(request) {
  const session = await (await request.get(`${ADMIN}/api/admin/session`)).json();
  if (!session.setupRequired) return;
  const state = await (await request.get(`${SCREEN}/api/state`)).json();
  const response = await request.post(`${ADMIN}/api/admin/setup`, {
    data: { code: state.setup.code, password: PASSWORD }, headers: { Origin: ADMIN },
  });
  expect(response.ok(), await response.text()).toBe(true);
}

/** Signs the page's browser context in (the cookie then also covers page.request). */
export async function signIn(page) {
  await ensureAdmin(page.request);
  const response = await page.request.post(`${ADMIN}/api/admin/login`, { data: { password: PASSWORD }, headers: { Origin: ADMIN } });
  expect(response.ok(), await response.text()).toBe(true);
}

export async function getSettings(request) {
  return (await request.get(`${ADMIN}/api/admin/settings`)).json();
}

export async function putSettings(request, settings) {
  const { revision } = await getSettings(request);
  const response = await request.put(`${ADMIN}/api/admin/settings`, { data: { settings, revision }, headers: { Origin: ADMIN } });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

/** Removes every upload that is not in use (after the settings were restored). */
export async function clearUploads(request) {
  const { uploads } = await (await request.get(`${ADMIN}/api/admin/uploads`)).json();
  for (const upload of uploads) await request.delete(`${ADMIN}/api/admin/uploads/${upload.id}`, { headers: { Origin: ADMIN } });
}

export async function upload(request, name = "logo.png", body = PNG) {
  const response = await request.post(`${ADMIN}/api/admin/uploads`, {
    data: body, headers: { Origin: ADMIN, "Content-Type": "image/png", "X-File-Name": encodeURIComponent(name) },
  });
  expect(response.ok(), await response.text()).toBe(true);
  return (await response.json()).upload;
}
