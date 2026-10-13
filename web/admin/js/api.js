// Talks to the kiosk's admin API. Errors carry the server's message (German) and the field path.

import { t } from "./strings.js";

const REQUEST_TIMEOUT_MS = 20_000;

export class ApiError extends Error {
  constructor(status, message, path = null, body = null) {
    super(message);
    this.status = status;
    this.path = path;
    this.body = body;
  }
}

let onUnauthorized = () => {};

export function whenSignedOut(callback) {
  onUnauthorized = callback;
}

export async function request(method, path, body, { raw = false, headers = {} } = {}) {
  const init = { method, headers: { ...headers }, credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) };
  if (body !== undefined) {
    if (raw) {
      init.body = body;
    } else {
      init.body = JSON.stringify(body);
      init.headers["Content-Type"] = "application/json";
    }
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, t.networkError);
  }
  const payload = (response.headers.get("Content-Type") ?? "").startsWith("application/json") ? await response.json() : null;
  if (!response.ok) {
    if (response.status === 401 && !path.endsWith("/login") && !path.endsWith("/setup")) onUnauthorized();
    const error = payload?.error ?? {};
    throw new ApiError(response.status, error.message ?? t.networkError, error.path ?? null, payload);
  }
  return payload;
}

export const api = {
  session: () => request("GET", "/api/admin/session"),
  setup: (code, password) => request("POST", "/api/admin/setup", { code, password }),
  login: (password) => request("POST", "/api/admin/login", { password }),
  logout: () => request("POST", "/api/admin/logout", {}),
  settings: () => request("GET", "/api/admin/settings"),
  saveSettings: (settings, revision) => request("PUT", "/api/admin/settings", { settings, revision }),
  uploads: () => request("GET", "/api/admin/uploads"),
  upload: (file) => request("POST", "/api/admin/uploads", file, {
    raw: true, headers: { "Content-Type": file.type || "application/octet-stream", "X-File-Name": encodeURIComponent(file.name) },
  }),
  deleteUpload: (id) => request("DELETE", `/api/admin/uploads/${encodeURIComponent(id)}`),
  status: () => request("GET", "/api/admin/status"),
  refresh: () => request("POST", "/api/admin/actions/refresh", {}),
  reloadScreen: () => request("POST", "/api/admin/actions/reload-screen", {}),
  changePassword: (current, next) => request("POST", "/api/admin/password", { current, new: next }),
  searchStops: (text) => request("GET", `/api/admin/transit/stops?query=${encodeURIComponent(text)}`),
  checkUpdates: () => request("POST", "/api/admin/updates/check", {}),
  catalog: async () => (await fetch("/shared/widgets.json", { cache: "no-store" })).json(),
};
