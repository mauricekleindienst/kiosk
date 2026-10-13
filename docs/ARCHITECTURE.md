# Architecture

```
Raspberry Pi
  systemd --user: kiosk.service  ->  python3 -m kiosk   (server/kiosk, stdlib only)
     | scheduler thread: Bright Sky (DWD) every 10 min, news feeds every 10 min
     | store: last good result per source, in memory and in ~/.cache/kiosk/*.json
     | HTTP on 127.0.0.1:8080: /api/state, /api/health, static files from web/
  desktop autostart: scripts/start-browser.sh  ->  chromium --kiosk http://127.0.0.1:8080/
     | web/: plain ES modules, no build step; polls /api/state every minute
```

## Server (`server/kiosk`)

- `config.py`: `config.default.json` deep-merged with the owner's `~/.config/kiosk/config.json`,
  validated at start (the service refuses to start with a clear message instead of failing later).
- `http_client.py`: the only place that opens connections (timeouts, size limit, user agent,
  proxy from the environment). A guard test fails if another module does.
- `weather.py`: Bright Sky `/current_weather`, `/weather` (hourly, 8 days) and `/alerts` into the
  screen model: current conditions, 12 hours, 7 days (days grouped by Berlin date; a partial last
  day is dropped), warnings sorted by severity. Sunrise and sunset are computed locally.
  A failing alerts call does not hide the forecast.
- `feeds.py`: RSS 2.0 and Atom; strips Google News' " - Outlet" suffix, HTML and double escapes;
  newest first, duplicates and items older than `maxAgeDays` dropped.
- `store.py`: atomic cache writes (temp file, fsync, rename); a failed refresh keeps the last good
  data and records the error; the cache is loaded at start so a reboot without network still shows
  the last state.
- `app.py`: scheduler (a failed source retries after 60 s), `/api/state`, static files with a
  strict CSP (no inline script or style), no directory listing.

## Screen (`web/`)

- `main.js` ticks every second but only changes the DOM when the minute changes; it renders the
  data once a minute and on font load and resize. A nightly reload (`display.reloadAt`) clears
  whatever a browser accumulates over weeks.
- Every block fits its panel: headlines and forecast days that would be cut are removed rather
  than clipped (`news-view.js`, `weather-view.js`).
- Times are formatted in the configured time zone (`format.js`), so a Pi on UTC still shows
  office time. Holidays of Hesse are computed in `holidays.js`.
- Text from feeds only ever enters the DOM through `textContent`.
- Icons are SVG shapes built in the DOM (`icons.js`) and colored by tokens.
- Sizes are in rem; the root size follows the viewport (`min(1vw, 1.7778vh)`), so the layout
  scales from 720p to 4K. Portrait screens get a single column.

## Design

White, quiet, no "AI look" (see the owner's guidelines): neutral panels with a hairline border,
status color only in icons, small text and tinted fills. All colors in `web/styles/tokens.css`;
guard tests check literal colors, weights, radii, frames on states, left bars and WCAG contrast
for every text and meaningful fill.

## Tests

| Suite | What |
|---|---|
| `server/tests` | config, feeds, weather model, sun times, scheduler and cache (fake upstream), HTTP server and headers, guards |
| `tests/scripts` | install, uninstall and browser start against a temporary home with stand-ins for sudo, systemctl, raspi-config and Chromium |
| `tests/unit` | formatting (time zones, ISO weeks, DST), holidays |
| `tests/guards` | design rules, contrast, CSP, server/screen icon contract, UI text rules |
| `tests/e2e` | the real server against a fake Bright Sky and fake feeds (`serve.mjs`), Chromium at 720p, 1080p, 1440p, 4K, ultrawide and portrait; stale and offline states; markup in feed text |
