// The admin interface: setup or login first, then the pages behind a navigation.

import { api, whenSignedOut } from "./api.js";
import { layoutView } from "./layout-view.js";
import { deviceView, mediaView, settingsView } from "./pages.js";
import { loadAll, store, subscribe } from "./store.js";
import { t } from "./strings.js";
import { button, field, h, toast } from "./ui.js";

const app = document.getElementById("app");
const PAGES = {
  layout: layoutView,
  media: mediaView,
  settings: settingsView,
  device: deviceView,
};

function currentPage() {
  const page = location.hash.replace("#", "");
  return PAGES[page] ? page : "layout";
}

function authForm({ title, intro, fields, submitLabel, onSubmit, footer }) {
  const error = h("p", { class: "form-error", role: "alert" });
  error.hidden = true;
  const submit = button(submitLabel, null, { variant: "primary", type: "submit" });
  const form = h("form", { class: "auth-card card" },
    h("h1", { class: "page-title", text: title }),
    h("p", { class: "muted", text: intro }),
    h("div", { class: "form" }, fields, error, submit),
    footer ? h("p", { class: "field-hint", text: footer }) : null);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    error.hidden = true;
    try {
      await onSubmit();
      await start();
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      submit.disabled = false;
    }
  });
  app.replaceChildren(h("main", { class: "auth" }, form));
  form.querySelector("input")?.focus();
}

function showSetup() {
  const code = h("input", { class: "input input-code", inputmode: "numeric", autocomplete: "one-time-code", maxLength: 7, required: true, name: "code" });
  const password = h("input", { class: "input", type: "password", autocomplete: "new-password", minLength: 8, required: true, name: "password" });
  const repeat = h("input", { class: "input", type: "password", autocomplete: "new-password", minLength: 8, required: true, name: "repeat" });
  authForm({
    title: t.setupTitle,
    intro: t.setupIntro,
    fields: [field(t.setupCode, code), field(t.setupPassword, password, { hint: t.setupPasswordHint }), field(t.setupRepeat, repeat)],
    submitLabel: t.setupSubmit,
    onSubmit: async () => {
      if (password.value !== repeat.value) throw new Error(t.passwordsDiffer);
      await api.setup(code.value.replace(/\s/g, ""), password.value);
    },
  });
}

function showLogin() {
  const password = h("input", { class: "input", type: "password", autocomplete: "current-password", required: true, name: "password" });
  authForm({
    title: t.loginTitle,
    intro: t.loginIntro,
    fields: [field(t.password, password)],
    submitLabel: t.loginSubmit,
    onSubmit: () => api.login(password.value),
    footer: t.loginForgot,
  });
}

let unsubscribe = null;

async function showApp() {
  await loadAll();
  let status = null;
  try {
    status = await api.status();
  } catch {
    // The layout works without it; the preview then assumes 16:9.
  }
  const content = h("main", { class: "content", id: "content", tabindex: "-1" });
  const nav = h("nav", { class: "nav", "aria-label": t.appTitle });
  const page = currentPage();
  for (const [key, label] of Object.entries(t.nav)) {
    nav.append(h("a", { class: "nav-link", href: `#${key}`, text: label, "aria-current": key === page ? "page" : null }));
  }
  const header = h("header", { class: "topbar" },
    h("a", { class: "skip-link", href: "#content", text: t.skipToContent }),
    h("p", { class: "brand", text: t.appTitle }),
    nav,
    button(t.logout, async () => {
      await api.logout().catch(() => {});
      start();
    }, { variant: "link" }));
  app.replaceChildren(header, content);
  unsubscribe?.();
  const rerender = PAGES[page](content, status);
  // Saves from elsewhere (undo, conflicts) redraw the page.
  unsubscribe = subscribe(() => {
    if (page !== "device" && !document.activeElement?.matches?.("input[type=text], input:not([type]), textarea, input[type=url], input[inputmode]")) rerender();
  });
}

export async function start() {
  let session;
  try {
    session = await api.session();
  } catch (error) {
    app.replaceChildren(h("main", { class: "auth" }, h("div", { class: "auth-card card" }, h("p", { text: error.message }), button(t.retry, start))));
    return;
  }
  if (session.setupRequired) showSetup();
  else if (!session.authenticated) showLogin();
  else await showApp();
}

whenSignedOut(() => {
  toast(t.sessionExpired, { tone: "error" });
  start();
});
addEventListener("hashchange", () => {
  if (store.settings) showApp();
});
start();
