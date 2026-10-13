"""Walks the window through every step with a stand-in backend (needs a display; CI uses Xvfb)."""

import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: E402
import core  # noqa: E402


class FakeBackend(SimpleNamespace):
    REPOSITORY = core.REPOSITORY

    def __init__(self, **kwargs):
        super().__init__(written=[], connected=[], **kwargs)

    current_branch = staticmethod(lambda: "main")
    installed = staticmethod(lambda: False)
    needs_sudo_password = staticmethod(lambda: False)
    valid_repository = staticmethod(core.valid_repository)
    config_path = staticmethod(lambda: "/nonexistent/config.json")
    admin_urls = staticmethod(lambda: ["http://192.168.1.50:8081", "http://kiosk.local:8081"])

    def checks(self):
        return [core.Check("Python", "ok", "3.11"), core.Check("Chromium", "missing", "wird nachinstalliert")]

    def ensure_key(self):
        return "ssh-ed25519 AAAA kiosk@test"

    def test_access(self, repository):
        return "key"

    def write_config(self, path, admin_enabled):
        self.written.append(admin_enabled)

    def connect_checkout(self, repository, branch, mode):
        self.connected.append((repository, branch, mode))

    def install_command(self, password=None, cec=False):
        return [sys.executable, "-c", "print('kiosk: installing'); print('kiosk: done')"], {}

    def uninstall_command(self):
        return [sys.executable, "-c", "print('kiosk: removed')"], {}


class SetupWindowTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as err:
            self.fail(f"no display for the installer test ({err}); run it under xvfb-run")
        self.addCleanup(self.root.destroy)
        self.backend = FakeBackend()
        self.window = app.SetupApp(self.root, self.backend)

    def labels(self):
        found = []

        def walk(widget):
            for child in widget.winfo_children():
                try:
                    found.append(child.cget("text"))
                except tk.TclError:
                    pass
                walk(child)

        walk(self.window.body)
        return found

    def wait_for(self, condition, what):
        for _ in range(300):
            self.root.update()
            if condition():
                return
            self.root.after(20)
        self.fail(f"waited in vain for {what}")

    def test_install_from_start_to_finish(self):
        self.assertIn("Willkommen", self.labels())
        self.window.forward()
        self.assertIn("Fehlt", self.labels())
        self.window.forward()
        self.window.admin.set(False)
        self.window.forward()
        self.window.forward()
        self.assertIn("Bitte erst", self.window.note.cget("text"), "updates need a checked access first")
        self.window.make_key()
        self.assertEqual(self.window.key_box.get("1.0", "end").strip(), "ssh-ed25519 AAAA kiosk@test")
        self.window.check_access()
        self.assertIn("Schlüssel funktioniert", self.window.note.cget("text"))
        self.window.forward()
        self.assertEqual(self.window.next.cget("text"), "Installieren")
        self.window.forward()
        self.wait_for(lambda: self.window.step == 5, "the done page")
        self.assertEqual(self.backend.written, [False])
        self.assertEqual(self.backend.connected, [(core.REPOSITORY, "main", "key")])
        self.assertIn("Fertig", self.labels())

    def test_a_failing_install_offers_a_retry(self):
        self.backend.install_command = lambda password=None, cec=False: ([sys.executable, "-c", "import sys; print('boom'); sys.exit(1)"], {})
        self.window.updates.set(False)
        self.window.step = 4
        self.window.show()
        self.window.forward()
        self.wait_for(lambda: not self.window.running, "the install to end")
        self.assertEqual(self.window.next.cget("text"), "Erneut versuchen")
        self.assertIn("boom", self.window.log.get("1.0", "end"))

    def test_remove_goes_straight_to_the_confirmation(self):
        self.backend.installed = lambda: True
        self.window.show()
        self.window.mode.set("remove")
        self.window.forward()
        self.assertEqual(self.window.next.cget("text"), "Entfernen")
        self.window.forward()
        self.wait_for(lambda: self.window.step == 5, "the done page")
        self.assertIn("Entfernt", self.labels())


if __name__ == "__main__":
    unittest.main()
