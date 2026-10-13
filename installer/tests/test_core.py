import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402


def result(code=0, out="", err=""):
    return SimpleNamespace(returncode=code, stdout=out, stderr=err)


class CoreTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)

    def test_checks_report_what_matters(self):
        release = self.home / "os-release"
        release.write_text('PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\n')
        found = {"git": "/usr/bin/git", "sudo": "/usr/bin/sudo"}
        checks = {c.label: c for c in core.checks({"WAYLAND_DISPLAY": "wayland-0"}, found.get, lambda args: result(1), (3, 11), release)}
        self.assertEqual(checks["Python"].state, "ok")
        self.assertEqual(checks["Chromium"].state, "missing")
        self.assertIn("nachinstalliert", checks["Chromium"].detail)
        self.assertEqual(checks["Desktop"].detail, "Wayland")
        self.assertEqual(checks["Administratorrechte"].state, "warn")
        old = {c.label: c for c in core.checks({}, found.get, lambda args: result(0), (3, 9), release)}
        self.assertEqual(old["Python"].state, "missing")
        self.assertEqual(old["Administratorrechte"].state, "ok")

    def test_config_keeps_other_keys(self):
        path = self.home / ".config" / "kiosk" / "config.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"port": 9000}))
        self.assertEqual(core.write_config(path, admin_enabled=False), {"port": 9000, "adminPort": None})
        self.assertEqual(core.write_config(path, admin_enabled=True), {"port": 9000})
        self.assertEqual(json.loads(path.read_text()), {"port": 9000})

    def test_deploy_key_and_ssh_alias_are_written_once(self):
        public = core.ensure_key(self.home, hostname="kiosk-test")
        self.assertTrue(public.startswith("ssh-ed25519 "))
        self.assertTrue(public.endswith("kiosk@kiosk-test"))
        self.assertEqual(core.ensure_key(self.home), public, "an existing key is kept")
        config = (self.home / ".ssh" / "config")
        config.write_text("Host other\n  User me\n\n" + config.read_text())
        core.write_ssh_config(self.home)
        text = config.read_text()
        self.assertEqual(text.count("Host github-kiosk"), 1)
        self.assertIn("Host other", text)
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)

    def test_repository_names_and_urls(self):
        self.assertTrue(core.valid_repository("mauricekleindienst/kiosk"))
        for bad in ("kiosk", "a/b/c", "a b/c", "", None, "../x"):
            self.assertFalse(core.valid_repository(bad), bad)
        self.assertEqual(core.remote_url("o/r", "public"), "https://github.com/o/r.git")
        self.assertEqual(core.remote_url("o/r", "key"), "git@github-kiosk:o/r.git")

    def test_access_prefers_public_then_key(self):
        self.assertEqual(core.test_access("o/r", lambda args, **kw: result(0)), "public")
        calls = []

        def key_only(args, **kw):
            calls.append(args[-1])
            return result(0 if args[-1].startswith("git@") else 128)

        self.assertEqual(core.test_access("o/r", key_only), "key")
        self.assertIsNone(core.test_access("o/r", lambda args, **kw: result(128)))

    def test_install_command_passes_the_password_only_through_the_environment(self):
        argv, env = core.install_command("geheim", cec=True, temp_dir=str(self.home))
        self.assertEqual(argv[-1].rsplit("/", 2)[-2:], ["scripts", "install.sh"])
        self.assertEqual(env["KIOSK_SUDO"], "sudo -A")
        self.assertEqual(env["KIOSK_CEC"], "1")
        helper = Path(env["SUDO_ASKPASS"])
        self.assertNotIn("geheim", helper.read_text(), "the password never lands in a file")
        out = subprocess.run([str(helper)], env={"KIOSK_SUDO_PASSWORD": "geheim"}, capture_output=True, text=True)
        self.assertEqual(out.stdout, "geheim\n")
        self.assertEqual(core.install_command()[1], {})


class ConnectCheckoutTest(unittest.TestCase):
    """A folder from a ZIP becomes a checkout that update.sh can fast-forward."""

    def git(self, cwd, *args):
        return subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.org", *args], cwd=cwd,
                              check=True, capture_output=True, text=True).stdout.strip()

    def test_zip_folder_becomes_a_tracking_checkout(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        source = root / "source"
        source.mkdir()
        (source / "README.md").write_text("kiosk\n")
        self.git(source, "init", "-q", "-b", "main")
        self.git(source, "add", "-A")
        self.git(source, "commit", "-q", "-m", "one")
        origin = root / "origin.git"
        self.git(root, "clone", "-q", "--bare", str(source), str(origin))
        unpacked = root / "kiosk-main"
        unpacked.mkdir()
        (unpacked / "README.md").write_text("kiosk\n")

        original = core.remote_url
        core.remote_url = lambda repository, mode: str(origin)
        self.addCleanup(setattr, core, "remote_url", original)
        core.connect_checkout("o/r", "main", "public", root=unpacked)
        self.assertEqual(self.git(unpacked, "rev-parse", "--abbrev-ref", "@{u}"), "origin/main")
        self.assertEqual(self.git(unpacked, "status", "--porcelain"), "")

        with self.assertRaisesRegex(RuntimeError, "fehlgeschlagen"):
            core.connect_checkout("o/r", "does-not-exist", "public", root=unpacked)


if __name__ == "__main__":
    unittest.main()
