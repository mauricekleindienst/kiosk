import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from kiosk.updates import Updater

from helpers import berlin

PROJECT = Path(__file__).resolve().parents[2]
PARTS = ("scripts", "server/kiosk", "web/shared/widgets.json", "config.default.json")


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.org", "-c", "init.defaultBranch=main", *args],
                          cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class UpdateScriptTest(unittest.TestCase):
    """scripts/update.sh against a real origin and a real clone in a temporary folder."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.source = root / "source"
        for part in PARTS:
            target = self.source / part
            target.parent.mkdir(parents=True, exist_ok=True)
            if (PROJECT / part).is_dir():
                shutil.copytree(PROJECT / part, target, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(PROJECT / part, target)
        git(self.source, "init", "-q")
        git(self.source, "add", "-A")
        git(self.source, "commit", "-q", "-m", "first")
        self.origin = root / "origin.git"
        git(root, "clone", "-q", "--bare", str(self.source), str(self.origin))
        git(self.source, "remote", "add", "origin", str(self.origin))
        self.device = root / "device"
        git(root, "clone", "-q", str(self.origin), str(self.device))

    def publish(self, path, text):
        (self.source / path).write_text(text, encoding="utf-8")
        git(self.source, "add", "-A")
        git(self.source, "commit", "-q", "-m", f"change {path}")
        git(self.source, "push", "-q", "origin", "HEAD:main")
        return git(self.source, "rev-parse", "HEAD")

    def update(self):
        result = subprocess.run(["bash", str(self.device / "scripts" / "update.sh")], capture_output=True, text=True, timeout=120)
        return result.returncode, result.stdout.strip()

    def head(self):
        return git(self.device, "rev-parse", "HEAD")

    def test_already_current(self):
        self.assertEqual(self.update()[0], 10)

    def test_fast_forward_to_the_new_commit(self):
        new = self.publish("NOTES.md", "neu\n")
        code, output = self.update()
        self.assertEqual(code, 0, output)
        self.assertEqual(self.head(), new)
        self.assertEqual((self.device / "NOTES.md").read_text(encoding="utf-8"), "neu\n")

    def test_local_changes_are_never_overwritten(self):
        self.publish("NOTES.md", "neu\n")
        (self.device / "config.default.json").write_text("{}", encoding="utf-8")
        old = self.head()
        self.assertEqual(self.update()[0], 30)
        self.assertEqual(self.head(), old)
        self.assertEqual((self.device / "config.default.json").read_text(encoding="utf-8"), "{}")

    def test_a_version_that_fails_its_self_test_is_rolled_back(self):
        old = self.head()
        self.publish("config.default.json", "{ broken")
        code, output = self.update()
        self.assertEqual(code, 50, output)
        self.assertEqual(self.head(), old)
        json.loads((self.device / "config.default.json").read_text(encoding="utf-8"))

    def test_without_upstream_or_git(self):
        git(self.device, "checkout", "-q", "-b", "local-only")
        self.assertEqual(self.update()[0], 20)
        shutil.rmtree(self.device / ".git")
        self.assertEqual(self.update()[0], 20)

    def test_unreachable_origin(self):
        shutil.rmtree(self.origin)
        self.assertEqual(self.update()[0], 40)


class UpdaterTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.status_path = Path(folder.name, "update-status.json")
        self.updated = threading.Event()
        self.code = 0

    def make(self):
        def run(*args, **kwargs):
            return SimpleNamespace(returncode=self.code, stdout="output")

        return Updater(lambda: berlin(2026, 10, 14, 3, 15), self.updated.set, self.status_path, run=run)

    def wait(self, updater):
        for _ in range(200):
            if not updater.status["running"]:
                return
            threading.Event().wait(0.01)
        self.fail("the update did not finish")

    def test_due_once_a_day_at_the_time_and_only_when_on(self):
        updater = self.make()
        settings = {"updates": {"enabled": True, "time": "03:15"}}
        self.assertFalse(updater.due(settings, datetime(2026, 10, 14, 3, 14)))
        self.assertTrue(updater.due(settings, datetime(2026, 10, 14, 3, 15)))
        self.assertFalse(updater.due(settings, datetime(2026, 10, 14, 3, 15)), "not twice in the same minute")
        self.assertTrue(updater.due(settings, datetime(2026, 10, 15, 3, 15)))
        self.assertFalse(updater.due({"updates": {"enabled": False, "time": "03:15"}}, datetime(2026, 10, 16, 3, 15)))

    def test_an_update_restarts_and_the_result_survives_the_restart(self):
        updater = self.make()
        self.assertTrue(updater.start())
        self.assertTrue(self.updated.wait(5), "the server is asked to restart")
        self.assertEqual(updater.status["result"], "updated")
        restarted = self.make()
        self.assertEqual(restarted.status["message"], "Aktualisiert. Der Kiosk startet neu.")
        self.assertEqual(restarted.status["lastCheck"], "2026-10-14T03:15:00+02:00")

    def test_failures_do_not_restart(self):
        self.code = 40
        updater = self.make()
        updater.start()
        self.wait(updater)
        self.assertFalse(self.updated.is_set())
        self.assertEqual(updater.status["result"], "failed")
        self.assertIn("Deploy Key", updater.status["message"])


if __name__ == "__main__":
    unittest.main()
