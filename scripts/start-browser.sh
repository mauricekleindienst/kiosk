#!/usr/bin/env bash
# Opens the kiosk screen fullscreen in Chromium as soon as the data server answers, and opens it
# again whenever the browser exits or crashes. Started by the desktop autostart (see install.sh).
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/kiosk/config.json"
PROFILE="${XDG_DATA_HOME:-$HOME/.local/share}/kiosk/chromium"

PORT="$(cd "$ROOT/server" && python3 -c 'import sys; from kiosk.config import load_config; print(load_config(sys.argv[1])["port"])' "$CONFIG")" || PORT=8080
URL="http://127.0.0.1:${PORT}/"

BROWSER="$(command -v chromium || command -v chromium-browser || true)"
if [ -z "$BROWSER" ]; then
  echo "kiosk: Chromium is not installed; run scripts/install.sh again." >&2
  exit 1
fi

# The server starts with the session; wait for it instead of showing an error page.
until curl -sf --max-time 2 "${URL}api/health" >/dev/null; do
  sleep 2
done

# The monitor follows the night schedule; the helper keeps its own lock, so it runs once.
"$ROOT/scripts/display-power.sh" &

mkdir -p "$PROFILE"
# Several autostart mechanisms may start this script (XDG, labwc, wayfire); only one may run.
exec 9>"$PROFILE.lock"
flock -n 9 || exit 0

while true; do
  # After a power cut Chromium would offer to restore the last session; tell it all went well.
  if [ -f "$PROFILE/Default/Preferences" ]; then
    sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]*"/"exit_type":"Normal"/' \
      "$PROFILE/Default/Preferences"
  fi
  "$BROWSER" \
    --kiosk \
    --user-data-dir="$PROFILE" \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --disable-session-crashed-bubble \
    --disable-features=Translate,TranslateUI \
    --check-for-update-interval=31536000 \
    --password-store=basic \
    --autoplay-policy=no-user-gesture-required \
    "$URL"
  sleep 5
done
