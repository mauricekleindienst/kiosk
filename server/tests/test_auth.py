import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from kiosk.auth import FREE_ATTEMPTS, SESSION_IDLE_SECONDS, SETUP_CODE_ATTEMPTS, Auth, AuthError


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class AuthTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name, "admin.json")
        self.clock = FakeClock()
        self.auth = Auth(self.path, clock=self.clock)

    def setup_admin(self, password="richtig-gut"):
        return self.auth.setup(self.auth.setup_code, password, "10.0.0.2")

    def test_setup_with_the_code_from_the_screen(self):
        self.assertTrue(self.auth.setup_required)
        self.assertRegex(self.auth.setup_code, r"^\d{6}$")
        token = self.setup_admin()
        self.assertTrue(self.auth.session_valid(token))
        self.assertFalse(self.auth.setup_required)
        self.assertIsNone(self.auth.setup_code, "the code is gone once a password exists")
        record = json.loads(self.path.read_text())
        self.assertNotIn("richtig-gut", self.path.read_text())
        self.assertEqual(set(record), {"salt", "hash", "n", "r", "p"})
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_setup_rejects_wrong_codes_and_rotates_the_code(self):
        code = self.auth.setup_code
        wrong = "000000" if code != "000000" else "111111"
        for attempt in range(SETUP_CODE_ATTEMPTS - 1):
            with self.assertRaisesRegex(AuthError, "Code stimmt nicht"):
                self.auth.setup(wrong, "richtig-gut", f"10.0.0.{attempt + 10}")
        with self.assertRaisesRegex(AuthError, "neuen Code"):
            self.auth.setup(wrong, "richtig-gut", "10.0.0.99")
        self.assertTrue(self.auth.setup_required)

    def test_setup_only_once_and_password_rules(self):
        with self.assertRaisesRegex(AuthError, "mindestens 8"):
            self.auth.setup(self.auth.setup_code, "kurz", "10.0.0.2")
        self.setup_admin()
        with self.assertRaises(AuthError) as caught:
            self.auth.setup("123456", "noch-ein-passwort", "10.0.0.3")
        self.assertEqual(caught.exception.status, 409)

    def test_login_logout(self):
        self.setup_admin()
        restarted = Auth(self.path, clock=self.clock)
        self.assertFalse(restarted.setup_required)
        with self.assertRaisesRegex(AuthError, "stimmt nicht"):
            restarted.login("falsch-falsch", "10.0.0.2")
        token = restarted.login("richtig-gut", "10.0.0.2")
        self.assertTrue(restarted.session_valid(token))
        restarted.logout(token)
        self.assertFalse(restarted.session_valid(token))
        self.assertFalse(restarted.session_valid(None))
        self.assertFalse(restarted.session_valid("made-up"))

    def test_lockout_after_wrong_passwords_per_address(self):
        self.setup_admin()
        for _ in range(FREE_ATTEMPTS):
            with self.assertRaises(AuthError):
                self.auth.login("falsch-falsch", "10.0.0.5")
        with self.assertRaises(AuthError) as caught:
            self.auth.login("richtig-gut", "10.0.0.5")
        self.assertEqual(caught.exception.status, 429, "even the right password waits during the lockout")
        self.assertTrue(self.auth.login("richtig-gut", "10.0.0.6"), "other addresses are not locked out")
        self.clock.now += 31
        self.assertTrue(self.auth.login("richtig-gut", "10.0.0.5"))

    def test_sessions_expire_when_idle(self):
        token = self.setup_admin()
        self.clock.now += SESSION_IDLE_SECONDS + 1
        self.assertFalse(self.auth.session_valid(token))

    def test_changing_the_password_signs_everybody_else_out(self):
        first = self.setup_admin()
        second = self.auth.login("richtig-gut", "10.0.0.3")
        with self.assertRaisesRegex(AuthError, "bisherige"):
            self.auth.change_password("falsch-falsch", "neues-passwort", "10.0.0.2")
        new_token = self.auth.change_password("richtig-gut", "neues-passwort", "10.0.0.2")
        self.assertFalse(self.auth.session_valid(first))
        self.assertFalse(self.auth.session_valid(second))
        self.assertTrue(self.auth.session_valid(new_token))
        self.assertTrue(self.auth.login("neues-passwort", "10.0.0.2"))

    def test_unreadable_password_file_fails_closed(self):
        self.path.write_text("{kaputt", encoding="utf-8")
        with self.assertLogs("kiosk", "ERROR"):
            auth = Auth(self.path, clock=self.clock)
        self.assertFalse(auth.setup_required, "a broken file must not reopen the setup")
        with self.assertRaises(AuthError):
            auth.login("irgendwas-langes", "10.0.0.2")


if __name__ == "__main__":
    unittest.main()
