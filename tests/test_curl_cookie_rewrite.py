import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.helpers import load_weread_bot


class CurlCookieRewriteTests(unittest.TestCase):
    """CURL 文本中 cookie 改写与原子写回的行为。"""

    def setUp(self):
        self.bot = load_weread_bot()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.temp_dir = Path(temp_dir.name)

    def test_update_rewrites_cookie_header_keeping_other_lines(self):
        source = (
            "curl 'https://weread.qq.com/web/book/read' \\\n"
            "  -H 'accept: application/json' \\\n"
            "  -H 'Cookie: wr_skey=old-key; wr_vid=1' \\\n"
            "  --data-raw '{\"appId\":\"app\"}'"
        )

        updated = self.bot.update_curl_cookie_value(source, "wr_skey", "new")

        self.assertEqual(updated, source.replace("old-key", "new"))

    def test_update_rewrites_dash_b_argument(self):
        source = "curl 'https://weread.qq.com/web/book/read' -b 'wr_skey=old'"

        updated = self.bot.update_curl_cookie_value(source, "wr_skey", "new")

        self.assertEqual(updated, source.replace("old", "new"))

    def test_update_rewrites_both_cookie_forms(self):
        source = "-H 'Cookie: wr_skey=old; wr_vid=1' -b 'wr_skey=old'"

        updated = self.bot.update_curl_cookie_value(source, "wr_skey", "new")

        self.assertEqual(updated, source.replace("old", "new"))

    def test_update_appends_missing_cookie(self):
        source = (
            "curl 'https://weread.qq.com/web/book/read' "
            "-H 'Cookie: wr_vid=1'"
        )

        updated = self.bot.update_curl_cookie_value(source, "wr_skey", "new")

        self.assertEqual(
            updated, source.replace("wr_vid=1", "wr_vid=1; wr_skey=new")
        )

    def test_update_returns_none_without_cookie_form(self):
        source = (
            "curl 'https://weread.qq.com/web/book/read' -H 'accept: */*'"
        )

        self.assertIsNone(
            self.bot.update_curl_cookie_value(source, "wr_skey", "new")
        )

    def test_write_is_atomic_replace_in_same_directory(self):
        target = self.temp_dir / "curl_command.txt"
        target.write_text("old", encoding="utf-8")
        real_replace = self.bot.os.replace
        replaced = []

        def record_replace(src, dst):
            replaced.append((Path(src), Path(dst)))
            real_replace(src, dst)

        with patch.object(self.bot.os, "replace", side_effect=record_replace):
            written = self.bot.write_curl_file_atomically(target, "new")

        self.assertTrue(written)
        self.assertEqual(target.read_text(encoding="utf-8"), "new")
        self.assertEqual(replaced[0][1], target)
        self.assertEqual(replaced[0][0].parent, target.parent)
        self.assertEqual(
            sorted(path.name for path in self.temp_dir.iterdir()),
            ["curl_command.txt"],
        )

    def test_write_failure_keeps_original_and_cleans_temp(self):
        target = self.temp_dir / "curl_command.txt"
        target.write_text("old", encoding="utf-8")

        with patch.object(
            self.bot.os, "replace", side_effect=OSError("readonly")
        ):
            with self.assertLogs(level="WARNING"):
                written = self.bot.write_curl_file_atomically(target, "new")

        self.assertFalse(written)
        self.assertEqual(target.read_text(encoding="utf-8"), "old")
        self.assertEqual(
            sorted(path.name for path in self.temp_dir.iterdir()),
            ["curl_command.txt"],
        )

    def test_write_creates_missing_file(self):
        target = self.temp_dir / "new.txt"

        written = self.bot.write_curl_file_atomically(target, "content")

        self.assertTrue(written)
        self.assertEqual(target.read_text(encoding="utf-8"), "content")


if __name__ == "__main__":
    unittest.main()
