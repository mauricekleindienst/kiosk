import re
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "kiosk"


class GuardTest(unittest.TestCase):
    def test_every_outbound_request_goes_through_the_http_client(self):
        for path in PACKAGE.glob("*.py"):
            if path.name == "http_client.py":
                continue
            source = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"^\s*(import|from)\s+(urllib\.request|http\.client|requests)\b|urlopen\(", source, re.M),
                f"{path.name} opens connections itself; use http_client.fetch",
            )

    def test_logs_go_through_the_kiosk_logger(self):
        for path in PACKAGE.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"^\s*print\(", f"{path.name} prints; use the kiosk logger")


if __name__ == "__main__":
    unittest.main()
