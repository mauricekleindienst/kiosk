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
    "curl": "exit 0",
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


if __name__ == "__main__":
    unittest.main()
