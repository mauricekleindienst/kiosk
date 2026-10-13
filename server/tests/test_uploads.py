import tempfile
import unittest
from pathlib import Path

from kiosk.uploads import MAX_BYTES, UploadError, Uploads, detect_type

from helpers import PNG


class UploadsTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name, "uploads")
        self.uploads = Uploads(self.dir)

    def test_types_come_from_the_content(self):
        self.assertEqual(detect_type(PNG), "png")
        self.assertEqual(detect_type(b"\xff\xd8\xff\xe0rest"), "jpg")
        self.assertEqual(detect_type(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "webp")
        self.assertEqual(detect_type(b"GIF89a..."), "gif")
        self.assertEqual(detect_type(b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"/>'), "svg")
        self.assertEqual(detect_type(b"\xef\xbb\xbf  <svg/>"), "svg")
        self.assertIsNone(detect_type(b"<html><script>alert(1)</script></html>"))
        self.assertIsNone(detect_type(b"MZ\x90\x00 executable"))

    def test_add_list_remove(self):
        item = self.uploads.add(PNG, "Firmen/Logo\x00.png")
        self.assertRegex(item["id"], r"^[0-9a-f]{20}\.png$")
        self.assertEqual(item["name"], "FirmenLogo.png", "slashes and control characters are dropped from the name")
        self.assertEqual(item["type"], "image/png")
        self.assertEqual(self.uploads.add(PNG, "again.png")["id"], item["id"], "the same file is stored once")
        self.assertEqual(len(Uploads(self.dir).list()), 1, "the index survives a restart")
        self.assertEqual(self.uploads.path(item["id"]).read_bytes(), PNG)
        self.uploads.remove(item["id"])
        self.assertEqual(self.uploads.list(), [])
        self.assertIsNone(self.uploads.path(item["id"]))

    def test_rejects_wrong_types_empty_and_huge_files(self):
        with self.assertRaises(UploadError) as caught:
            self.uploads.add(b"<html></html>", "page.html")
        self.assertEqual(caught.exception.status, 415)
        with self.assertRaises(UploadError):
            self.uploads.add(b"", "empty.png")
        with self.assertRaises(UploadError) as caught:
            self.uploads.add(PNG + b"\x00" * MAX_BYTES, "huge.png")
        self.assertEqual(caught.exception.status, 413)

    def test_paths_never_leave_the_folder(self):
        for upload_id in ("../admin.json", "uploads.json", "0123456789abcdef0123.exe", "/etc/passwd", None):
            self.assertIsNone(self.uploads.path(upload_id))

    def test_removing_an_unknown_upload(self):
        with self.assertRaises(UploadError) as caught:
            self.uploads.remove("0123456789abcdef0123.png")
        self.assertEqual(caught.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
