# Working on Kiosk

An office wall screen for a Raspberry Pi with an admin interface for the local network. A
stdlib-only Python server (`server/kiosk`) fetches and caches weather and news, stores the settings
and serves the screen (`web/screen`, to Chromium in kiosk mode on 127.0.0.1) and the admin interface
(`web/admin`, port 8081 in the network); shared code, tokens and the widget catalog are in
`web/shared`; the Raspberry Pi setup is in `scripts/`. Read `docs/ARCHITECTURE.md` and `README.md` first. Follow
https://github.com/mauricekleindienst/AICodeGuidelines (read its CLAUDE.md first); this file wins
where it is more specific.

## Owner decisions (standing)

- Commits are authored as `Maurice Kleindienst <kleindiema@gmail.com>` (see owner.md). No co-author
  or session trailers, no assistant or model names in commits, code, comments or docs.
- No pull requests unless asked. No force push, branch deletion or history rewrite without an
  explicit request.
- Secrets only in the OS credential store or the environment's secret settings. The screen needs
  none today; keep it that way where possible.
- UI German only ("du"), texts in `web/screen/js/strings.js`, `web/admin/js/strings.js` and the
  catalog `web/shared/widgets.json`; README in German.
- The wall screen is white only (the owner asked for a white screen). The admin interface follows
  the device's light or dark theme.
- Admin interface in the local network over plain HTTP on port 8081; first setup only with the
  six-digit code the screen shows (proves physical presence); one admin password, no user accounts.
- Settings apply instantly with undo. Exception: the password change is a form with an explicit
  button (it needs the current password).
- Layout grid 12 x 8 cells; widget types and their options come from `web/shared/widgets.json`.
- Runtime on the Pi: only what Raspberry Pi OS ships (Python 3.11+, Chromium, curl). No Node, no pip
  packages, no build step. Node and Playwright are for tests only.
- Data sources: weather from DWD open data via Bright Sky (no key, commercial use allowed);
  news from Google News RSS searches, configurable to any RSS/Atom feed.

## Code rules

- Match the surrounding style and comment density. No emojis anywhere.
- UI texts go through the string catalogs; the content guard checks emoji, ellipsis, dashes and "du".
- Use the design tokens in `web/shared/styles/tokens.css`; no one-off colors.
- A new widget type: add it to `widgets.json`, a module in `web/screen/js/widgets/` registered in
  `index.js`, styles in `screen.css`, and it into the "every widget type" e2e layout.
- No accent-colored borders, outlines, left bars, glows or gradient borders for any state; quiet
  neutral tint and text weight instead. Focus visible only on `:focus-visible`, neutral.
- CSP without `unsafe-inline`: no inline script, style or style attributes; custom properties via
  the CSSOM are fine.
- Every outbound request goes through `server/kiosk/http_client.py`; feed text and settings reach
  the DOM only through `textContent` (no `innerHTML`, guarded).
- Admin API: every write needs a session and a same-origin `Origin`; the setup code never leaves
  the screen port.

## Checks

```
shellcheck scripts/*.sh
npm run test:server
npm run test:scripts
npm run test:unit
npm run test:e2e
```

Never kill processes by name or pattern; kill only PIDs you started. Prefer root-cause fixes; never
skip or weaken a test.

## Release

Push to `main`; on the Pi: `cd ~/kiosk && git pull && systemctl --user restart kiosk`.
