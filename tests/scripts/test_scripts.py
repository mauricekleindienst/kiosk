"""Runs the Raspberry Pi scripts against a temporary home with stand-ins for sudo, systemctl,
raspi-config and Chromium, and checks what they leave behind."""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUBS = {
    "sudo": 'echo "sudo $*" >> "$STUB_LOG"',
    "systemctl": 'echo "systemctl $*" >> "$STUB_LOG"',
    "raspi-config": 'echo "raspi-config $*" >> "$STUB_LOG"',
    # The display helper asks the server; the test decides the answer.
    "curl": 'printf "%s" "${CURL_ANSWER:-}"',
    "wlr-randr": 'if [ $# -eq 0 ]; then printf "HDMI-A-1 \\"Dell U2720Q\\"\\n  Enabled: yes\\nHDMI-A-2 \\"TV\\"\\n  Enabled: yes\\n"; else echo "wlr-randr $*" >> "$STUB_LOG"; fi',
    "cec-ctl": 'echo "cec-ctl $*" >> "$STUB_LOG"',
    "xset": 'echo "xset $*" >> "$STUB_LOG"',
    # The tests may run as root (containers); the scripts must believe they run as a normal user.
    "id": "echo 1000",
    # Records its arguments, then ends the endless relaunch loop of start-browser.sh.
    "chromium": 'echo "chromium $*" >> "$STUB_LOG"; kill -TERM "$PPID"',
}


class ScriptsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name, "home")
        self.config = self.home / ".config"
        bin_dir = Path(self.tmp.name, "bin")
        bin_dir.mkdir()
        for name, body in STUBS.items():
            path = bin_dir / name
            path.write_text(f"#!/usr/bin/env bash\n{body}\n")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        self.log = Path(self.tmp.name, "calls.log")
        self.log.touch()
        self.env = {
            "HOME": str(self.home),
            "USER": "pi",
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_LOG": str(self.log),
            # The display helper runs one round in tests instead of looping forever.
            "KIOSK_DISPLAY_ONCE": "1",
        }

    def run_script(self, name, check=True):
        return subprocess.run(
            ["bash", str(ROOT / "scripts" / name)], env=self.env, capture_output=True, text=True, check=check, timeout=30,
        )

    def test_install_sets_up_service_autostart_and_blanking(self):
        (self.config / "labwc").mkdir(parents=True)
        (self.config / "wayfire.ini").write_text("[core]\nplugins = autostart\n\n[autostart]\npanel = wfrespawn wf-panel-pi\n")

        self.run_script("install.sh")
        self.run_script("install.sh")  # a second run must not duplicate anything

        unit = (self.config / "systemd/user/kiosk.service").read_text()
        self.assertIn(f"WorkingDirectory={ROOT}/server", unit)
        self.assertIn("Restart=always", unit)
        desktop = (self.config / "autostart/kiosk-browser.desktop").read_text()
        self.assertIn(f"Exec={ROOT}/scripts/start-browser.sh", desktop)
        launcher = str(ROOT / "scripts/start-browser.sh")
        self.assertEqual((self.config / "labwc/autostart").read_text().count(launcher), 1)
        wayfire = (self.config / "wayfire.ini").read_text()
        self.assertEqual(wayfire.count(launcher), 1)
        self.assertIn("panel = wfrespawn wf-panel-pi", wayfire, "existing autostart entries stay")

        calls = self.log.read_text()
        self.assertIn("systemctl --user enable kiosk.service", calls)
        self.assertIn("sudo loginctl enable-linger pi", calls)
        self.assertIn("sudo raspi-config nonint do_blanking 1", calls)
        self.assertNotIn("apt-get", calls, "Chromium is present; nothing to install")

    def test_install_refuses_an_invalid_configuration(self):
        (self.config / "kiosk").mkdir(parents=True)
        (self.config / "kiosk/config.json").write_text('{"location": {"lat": 200}}')
        result = self.run_script("install.sh", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lat", result.stderr)
        self.assertFalse((self.config / "systemd/user/kiosk.service").exists())

    def test_uninstall_removes_what_install_added(self):
        (self.config / "labwc").mkdir(parents=True)
        self.run_script("install.sh")
        self.run_script("uninstall.sh")
        self.assertFalse((self.config / "systemd/user/kiosk.service").exists())
        self.assertFalse((self.config / "autostart/kiosk-browser.desktop").exists())
        self.assertNotIn("start-browser.sh", (self.config / "labwc/autostart").read_text())

    def test_browser_opens_the_configured_port_in_kiosk_mode(self):
        (self.config / "kiosk").mkdir(parents=True)
        (self.config / "kiosk/config.json").write_text('{"port": 8123}')
        self.run_script("start-browser.sh", check=False)
        call = self.log.read_text()
        self.assertIn("--kiosk", call)
        self.assertIn("http://127.0.0.1:8123/", call)
        self.assertIn(f"--user-data-dir={self.home}/.local/share/kiosk/chromium", call)


    def run_display(self, answer, **env):
        self.env.update(CURL_ANSWER=answer, **env)
        result = self.run_script("display-power.sh")
        return result.stdout, self.log.read_text()

    def test_night_switches_every_wayland_output_off(self):
        output, calls = self.run_display('{"on": false, "powerOff": true, "cec": false}', WAYLAND_DISPLAY="wayland-0")
        self.assertIn("display off", output)
        self.assertIn("wlr-randr --output HDMI-A-1 --off", calls)
        self.assertIn("wlr-randr --output HDMI-A-2 --off", calls)
        self.assertNotIn("cec-ctl", calls)

    def test_day_switches_on_and_wakes_the_tv(self):
        _, calls = self.run_display('{"on": true, "powerOff": true, "cec": true}', WAYLAND_DISPLAY="wayland-0")
        self.assertIn("wlr-randr --output HDMI-A-1 --on", calls)
        self.assertIn("cec-ctl --playback --to 0 --image-view-on", calls)

    def test_black_only_leaves_the_signal_on_but_still_sends_cec(self):
        _, calls = self.run_display('{"on": false, "powerOff": false, "cec": true}', WAYLAND_DISPLAY="wayland-0")
        self.assertNotIn("wlr-randr --output", calls)
        self.assertIn("cec-ctl --playback --to 0 --standby", calls)

    def test_x11_uses_dpms(self):
        _, calls = self.run_display('{"on": false, "powerOff": true, "cec": false}', DISPLAY=":0")
        self.assertIn("xset dpms force off", calls)

    def test_no_answer_changes_nothing(self):
        output, calls = self.run_display("", WAYLAND_DISPLAY="wayland-0")
        self.assertEqual(output, "")
        self.assertEqual(calls, "")


if __name__ == "__main__":
    unittest.main()
