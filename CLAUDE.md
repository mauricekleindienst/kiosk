# Working on Kiosk

An office wall screen for a Raspberry Pi: clock, date, holidays of Hesse, DWD weather for Kassel
and news feeds (Rheinmetall, region). A stdlib-only Python server (`server/kiosk`) fetches and
caches the data and serves a plain HTML/CSS/JS screen (`web/`) to Chromium in kiosk mode; the
Raspberry Pi setup is in `scripts/`. Read `docs/ARCHITECTURE.md` and `README.md` first. Follow
https://github.com/mauricekleindienst/AICodeGuidelines (read its CLAUDE.md first); this file wins
where it is more specific.

## Owner decisions (standing)

- Commits are authored as `Maurice Kleindienst <kleindiema@gmail.com>` (see owner.md). No co-author
  or session trailers, no assistant or model names in commits, code, comments or docs.
- No pull requests unless asked. No force push, branch deletion or history rewrite without an
  explicit request.
- Secrets only in the OS credential store or the environment's secret settings. The screen needs
  none today; keep it that way where possible.
- UI German only, texts in `web/js/strings.js`; README in German.
- White, light design only (the owner asked for a white screen); no dark theme.
- Runtime on the Pi: only what Raspberry Pi OS ships (Python 3.11+, Chromium, curl). No Node, no pip
  packages, no build step. Node and Playwright are for tests only.
- Data sources: weather from DWD open data via Bright Sky (no key, commercial use allowed);
  news from Google News RSS searches, configurable to any RSS/Atom feed.

## Code rules

- Match the surrounding style and comment density. No emojis anywhere.
- UI texts go through `web/js/strings.js`; the content guard checks emoji, ellipsis and dashes.
- Use the design tokens in `web/styles/tokens.css`; no one-off colors.
- No accent-colored borders, outlines, left bars, glows or gradient borders for any state; quiet
  neutral tint and text weight instead. Focus visible only on `:focus-visible`, neutral.
- CSP without `unsafe-inline`: no inline script, style or style attributes; custom properties via
  the CSSOM are fine.
- Every outbound request goes through `server/kiosk/http_client.py`; feed text reaches the DOM only
  through `textContent`.

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
