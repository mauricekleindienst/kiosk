#!/usr/bin/env bash
# Removes the kiosk service and autostart entry. Keeps the configuration and the cached data.
set -euo pipefail

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

systemctl --user disable --now kiosk.service 2>/dev/null || true
rm -f "$CONFIG_HOME/systemd/user/kiosk.service" "$CONFIG_HOME/autostart/kiosk-browser.desktop" \
  "${XDG_DATA_HOME:-$HOME/.local/share}/applications/kiosk-setup.desktop"
LAUNCHER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/start-browser.sh"
for file in "$CONFIG_HOME/labwc/autostart" "$CONFIG_HOME/wayfire.ini"; do
  if [ -f "$file" ]; then sed -i "\#$LAUNCHER#d" "$file"; fi
done
systemctl --user daemon-reload
printf 'kiosk: removed. Screen blanking stays off; switch it on again with sudo raspi-config.\n'
