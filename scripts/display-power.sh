#!/usr/bin/env bash
# Switches the monitor off and on following the night schedule of the kiosk server. Runs inside the
# desktop session (started by start-browser.sh): only there the display tools reach the screen.
#   Wayland (labwc, wayfire): wlr-randr turns the outputs off, so the monitor gets no signal and sleeps.
#   X11: DPMS through xset.
#   TVs: optionally standby and wake over HDMI-CEC with cec-ctl (package v4l-utils).
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/kiosk/config.json"
PROFILE="${XDG_DATA_HOME:-$HOME/.local/share}/kiosk"
INTERVAL="${KIOSK_DISPLAY_INTERVAL:-30}"

PORT="$(cd "$ROOT/server" && python3 -c 'import sys; from kiosk.config import load_config; print(load_config(sys.argv[1])["port"])' "$CONFIG")" || PORT=8080
URL="http://127.0.0.1:${PORT}/api/display"

mkdir -p "$PROFILE"
exec 8>"$PROFILE/display-power.lock"
flock -n 8 || exit 0

set_signal() {
  if [ -n "${WAYLAND_DISPLAY:-}" ] && command -v wlr-randr >/dev/null; then
    # Output names are the lines that do not start with a space ("HDMI-A-1 ...").
    wlr-randr | awk '/^[^ ]/ {print $1}' | while read -r output; do
      wlr-randr --output "$output" "--$1"
    done
  elif [ -n "${DISPLAY:-}" ] && command -v xset >/dev/null; then
    xset dpms force "$1"
  fi
}

set_cec() {
  command -v cec-ctl >/dev/null || return 0
  if [ "$1" = off ]; then
    cec-ctl --playback --to 0 --standby >/dev/null
  else
    cec-ctl --playback --to 0 --image-view-on >/dev/null
  fi
}

state=""
while true; do
  if answer="$(curl -sf --max-time 5 "$URL")"; then
    # "on|off powerOff cec", e.g. "off 1 0".
    read -r want power_off cec <<<"$(python3 -c 'import json, sys
d = json.load(sys.stdin)
print("on" if d["on"] else "off", int(d["powerOff"]), int(d["cec"]))' <<<"$answer" 2>/dev/null)"
    if [ -n "${want:-}" ] && [ "$want" != "$state" ]; then
      if [ "$want" = off ]; then
        [ "$power_off" = 1 ] && set_signal off
        [ "$cec" = 1 ] && set_cec off
      else
        # Switching on is harmless when it already is, so it also covers a restart at night.
        set_signal on
        [ "$cec" = 1 ] && set_cec on
      fi
      echo "kiosk: display $want"
      state="$want"
    fi
  fi
  [ -n "${KIOSK_DISPLAY_ONCE:-}" ] && exit 0
  sleep "$INTERVAL"
done
