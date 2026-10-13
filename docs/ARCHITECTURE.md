# Architecture

```
Raspberry Pi
  systemd --user: kiosk.service  ->  python3 -m kiosk   (server/kiosk, stdlib only)
     | scheduler thread: weather for the location and every distinct news feed, every 10 min
     | store: last good result per source, in memory and in ~/.cache/kiosk/*.json
     | screen port 127.0.0.1:8080: the screen, /api/state, /api/revision, /api/health, /uploads/
     | admin port 0.0.0.0:8081: the admin interface, /api/admin/*, the screen as preview (/screen/)
  desktop autostart: scripts/start-browser.sh  ->  chromium --kiosk http://127.0.0.1:8080/
     | web/screen: tiles from the settings; asks /api/revision every 3 s, /api/state on change
  any device in the network  ->  http://<pi>:8081  (web/admin)
```

## Server (`server/kiosk`)

- `config.py`: `config.default.json` deep-merged with the owner's `~/.config/kiosk/config.json`
  (ports, refresh intervals, the seed for the first layout), validated at start.
- `settings.py`: the editable settings (layout, widgets and their options, location, display),
  validated against the widget catalog `web/shared/widgets.json`, which the admin forms and the
  screen read as well. Stored atomically in `~/.config/kiosk/settings.json` with a revision; a
  save with an old revision is a conflict (two admins). Invalid files fall back to the defaults.
- `auth.py`: one admin password (scrypt, file mode 600), server-side sessions (12 h idle, 7 days
  max), a per-address lockout that doubles, and the six-digit setup code that only the local screen
  shows until a password exists. A broken password file fails closed.
- `uploads.py`: images stored under a content hash; the type comes from the bytes (PNG, JPEG, WebP,
  GIF, SVG), never from the client; SVGs are served with a sandboxing CSP.
- `http_api.py`: the two handlers. Static files resolve inside their folder only. Every admin
  write needs a session and a same-origin `Origin` header; JSON only; size limits.
- `weather.py`, `feeds.py`, `store.py`, `http_client.py`: as before: Bright Sky into the screen
  model, RSS and Atom into headlines, atomic cache, the one HTTP client.
- `app.py`: the sources follow the settings (one weather source per location, one news source per
  distinct URL, so two tiles with one feed fetch once); `/api/revision` tells the screen when
  settings, data, the setup state or a reload request changed.

## Screen (`web/screen`)

- Tiles on a 12 x 8 CSS grid, placed through the CSSOM. Each tile is a size container: parts that
  do not fit are left out (container queries), lists drop items that would be cut, messages shrink
  their text until it fits, big numbers scale with the tile.
- `widgets/*.js`: one module per type with `create(tile, widget, ctx)` returning `render` (data)
  and `tick` (time). The clock ticks every second but changes the DOM only when its text changes.
- Times follow the configured time zone; holidays of Hesse are computed in `shared/js/holidays.js`.
- Night mode hides the tiles on a black page; the setup notice is a fixed band at the bottom.
- The nightly reload only happens when the server answers.

## Admin (`web/admin`)

- `app.js`: setup with the code, login, then four pages (Layout, Logo und Bilder, Einstellungen,
  Gerät) behind a hash router.
- `store.js`: every change saves at once, one save after the other, with undo in the toast. A
  conflict loads the server's state; a field error (path from the server) shows at the field.
- `layout-view.js`: the grid editor (pointer drag to move, corner to resize, arrows and
  Shift+arrows, Delete with a confirmation that starts on Cancel), the inspector built from the
  catalog (`forms.js`), new tiles and templates (`templates.js`), and a live preview (the real
  screen in an iframe, scaled).
- Light and dark theme follow the device; the wall screen stays white (owner decision).

## Design

White, quiet, no "AI look" (see the owner's guidelines): neutral panels with a hairline border,
status color only in icons, small text and tinted fills; selected and current states are a neutral
tint plus weight. All colors, weights, radii and layers in `web/shared/styles/tokens.css`; guard
tests check literal colors, weights, layers, radii, frames on states, left bars and WCAG contrast in
both themes, including 3:1 for control borders.

## Tests

| Suite | What |
|---|---|
| `server/tests` | config, settings validation, auth (setup code, lockout, sessions), uploads, feeds, weather model, sun times, scheduler and cache, both HTTP ports (CSRF, traversal, sessions, conflicts), guards |
| `tests/scripts` | install, uninstall and browser start against a temporary home with stand-ins |
| `tests/unit` | formatting (time zones, ISO weeks, DST), holidays, grid geometry |
| `tests/guards` | design rules, contrast in both themes, CSP, no `innerHTML`, icon and widget contracts, templates, UI text rules |
| `tests/e2e` | the real server against a fake Bright Sky and fake feeds (`serve.mjs`): setup with the screen's code, login, keyboard and pointer editing with undo, live updates on the screen, logo upload, templates, settings, night mode, device page, password change, admin at 360 to 1920 px; the screen at six sizes, every widget type at every size (nothing cut, no tiny text), stale and offline states, markup in feed text |
