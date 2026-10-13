#!/usr/bin/env bash
# Sets up this Raspberry Pi as the office kiosk: the data server as a user service, Chromium in
# kiosk mode on login, no screen blanking. Run it as the desktop user, from the repository:
#   ./scripts/install.sh
# Running it again is safe; it updates what is there.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CONFIG="$CONFIG_HOME/kiosk/config.json"
UNIT_DIR="$CONFIG_HOME/systemd/user"
AUTOSTART_DIR="$CONFIG_HOME/autostart"

say() { printf 'kiosk: %s\n' "$*"; }
fail() { printf 'kiosk: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || fail "run this as the desktop user (e.g. pi), not as root; it asks for sudo where needed."

python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
  || fail "Python 3.11 or newer is needed (Raspberry Pi OS Bookworm or later)."

if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
  say "installing Chromium…"
  sudo apt-get update
  sudo apt-get install -y chromium
fi
command -v curl >/dev/null || { say "installing curl…"; sudo apt-get install -y curl; }

# Fail now, with the reason, rather than in a service log after the next reboot.
(cd "$ROOT/server" && python3 -c 'import sys; from kiosk.config import load_config; load_config(sys.argv[1])' "$CONFIG") \
  || fail "the configuration in $CONFIG is not valid (see the message above)."

say "installing the data server as a user service…"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/kiosk.service" <<UNIT
[Unit]
Description=Kiosk data server (weather and news for the office screen)

[Service]
WorkingDirectory=$ROOT/server
ExecStart=/usr/bin/env python3 -m kiosk
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable kiosk.service
systemctl --user restart kiosk.service
# Start the user services at boot, before anybody logs in.
sudo loginctl enable-linger "$USER"

say "opening the screen in Chromium on every login…"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/kiosk-browser.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Kiosk
Comment=Opens the office screen fullscreen
Exec=$ROOT/scripts/start-browser.sh
X-GNOME-Autostart-enabled=true
DESKTOP

# Raspberry Pi OS compositors: labwc (current) and wayfire (Bookworm before late 2024) have their
# own autostart files; the lock in start-browser.sh keeps it to one browser.
LAUNCHER="$ROOT/scripts/start-browser.sh"
if [ -d "$CONFIG_HOME/labwc" ] || [ -f /etc/xdg/labwc/autostart ]; then
  LABWC="$CONFIG_HOME/labwc/autostart"
  mkdir -p "$CONFIG_HOME/labwc"
  # A user file replaces the system one; start from it so the desktop keeps its panel and displays.
  if [ ! -f "$LABWC" ] && [ -f /etc/xdg/labwc/autostart ]; then cp /etc/xdg/labwc/autostart "$LABWC"; fi
  grep -qF "$LAUNCHER" "$LABWC" 2>/dev/null || printf '%s &\n' "$LAUNCHER" >> "$LABWC"
fi
WAYFIRE="$CONFIG_HOME/wayfire.ini"
if [ -f "$WAYFIRE" ] && ! grep -qF "$LAUNCHER" "$WAYFIRE"; then
  if grep -q '^\[autostart\]' "$WAYFIRE"; then
    sed -i "/^\[autostart\]/a kiosk = $LAUNCHER" "$WAYFIRE"
  else
    printf '\n[autostart]\nkiosk = %s\n' "$LAUNCHER" >> "$WAYFIRE"
  fi
fi

if command -v raspi-config >/dev/null; then
  say "switching off screen blanking…"
  sudo raspi-config nonint do_blanking 1
fi

say "done. The screen opens after the next reboot (sudo reboot)."
say "admin interface: http://$(hostname).local:8081 from any device in the network;"
say "  the first time, enter the code the screen shows. Logs: journalctl --user -u kiosk"
