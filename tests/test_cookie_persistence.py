import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.helpers import FakeHttpClient, load_weread_bot


CURL_HEADERS = (
    "curl 'https://weread.qq.com/web/book/read' \\\n"
    "  -H 'accept: application/json' \\\n"
    "  -H 'Cookie: wr_skey={skey}; wr_vid=12345678; wr_rt=abc' \\\n"
    "  --data-raw '{{\"appId\":\"app\",\"ps\":\"ps1\",\"pc\":\"pc1\"}}'"
)


class CookiePersistenceTests(unittest.IsolatedAsyncioTestCase):
    """续期成功后把新 wr_skey 写回 CURL 来源文件的回归测试。"""

    def setUp(self):
        self.bot = load_weread_bot()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.curl_file = Path(temp_dir.name) / "curl_command.txt"

    def _write_source(self, text):
        self.curl_file.write_text(text, encoding="utf-8")
        return text

    def _session(self, responses, source_file=None):
        session = object.__new__(self.bot.WeReadSessionManager)
        session.user_config = None
        session.user_name = "alice"
        session.config = self.bot.WeReadConfig(
            hack=self.bot.HackConfig(cookie_refresh_ql=True)
        )
        session.http_client = FakeHttpClient(raw_responses=responses)
        session.headers = {}
        session.cookies = {"wr_skey": "old-key"}
        session._curl_source_file = source_file
        return session

    @staticmethod
    def _cookie_response(wr_skey):
        response = MagicMock()
        response.cookies.get.return_value = wr_skey
        response.headers.get.return_value = ""
        return response

    def _leftover_files(self):
        return sorted(
            path.name
            for path in self.curl_file.parent.iterdir()
            if path.name != self.curl_file.name
        )

    def _read_source(self):
        return self.curl_file.read_text(encoding="utf-8")

    async def test_refresh_writes_new_skey_back_to_cookie_header(self):
        self._write_source(CURL_HEADERS.format(skey="old-key"))
        session = self._session(
            [(self._cookie_response("new-key"), 0.01)],
            source_file=str(self.curl_file),
        )

        refreshed = await session._refresh_cookie()

        self.assertTrue(refreshed)
        self.assertEqual(session.cookies["wr_skey"], "new-key")
        self.assertEqual(
            self._read_source(), CURL_HEADERS.format(skey="new-key")
        )

    async def test_refresh_writes_back_cookie_b_argument(self):
        source = (
            "curl 'https://weread.qq.com/web/book/read' "
            "-b 'wr_skey=old-key; wr_vid=1'"
        )
        self._write_source(source)
        session = self._session(
            [(self._cookie_response("new-key"), 0.01)],
            source_file=str(self.curl_file),
        )

        await session._refresh_cookie()

        self.assertEqual(
            self._read_source(), source.replace("old-key", "new-key")
        )

    async def test_write_back_replaces_file_atomically(self):
        self._write_source(CURL_HEADERS.format(skey="old-key"))
        session = self._session(
            [(self._cookie_response("new-key"), 0.01)],
            source_file=str(self.curl_file),
        )
        real_replace = self.bot.os.replace
        replaced = []

        def record_replace(src, dst):
            replaced.append((Path(src), Path(dst)))
            self.assertTrue(Path(src).exists())
            real_replace(src, dst)

        with patch.object(self.bot.os, "replace", side_effect=record_replace):
            await session._refresh_cookie()

        self.assertEqual(len(replaced), 1)
        temp_path, target = replaced[0]
        self.assertEqual(target, self.curl_file)
        self.assertEqual(temp_path.parent, self.curl_file.parent)
        self.assertNotEqual(temp_path, self.curl_file)
        self.assertEqual(self._leftover_files(), [])

    async def test_inline_source_keeps_file_untouched(self):
        original = self._write_source(CURL_HEADERS.format(skey="old-key"))
        before = self.curl_file.stat().st_mtime_ns
        session = self._session([(self._cookie_response("new-key"), 0.01)])

        refreshed = await session._refresh_cookie()

        self.assertTrue(refreshed)
        self.assertEqual(session.cookies["wr_skey"], "new-key")
        self.assertEqual(self._read_source(), original)
        self.assertEqual(self.curl_file.stat().st_mtime_ns, before)

    async def test_failed_refresh_does_not_write_file(self):
        original = self._write_source(CURL_HEADERS.format(skey="old-key"))
        session = self._session(
            [(self._cookie_response(None), 0.01)] * 3,
            source_file=str(self.curl_file),
        )

        with self.assertLogs(level="ERROR"):
            refreshed = await session._refresh_cookie()

        self.assertFalse(refreshed)
        self.assertEqual(session.cookies["wr_skey"], "old-key")
        self.assertEqual(self._read_source(), original)
        self.assertEqual(self._leftover_files(), [])

    async def test_write_failure_keeps_original_file(self):
        original = self._write_source(CURL_HEADERS.format(skey="old-key"))
        session = self._session(
            [(self._cookie_response("new-key"), 0.01)],
            source_file=str(self.curl_file),
        )

        with patch.object(
            self.bot.os, "replace", side_effect=OSError("readonly")
        ):
            with self.assertLogs(level="WARNING") as captured:
                refreshed = await session._refresh_cookie()

        self.assertTrue(refreshed)
        self.assertEqual(session.cookies["wr_skey"], "new-key")
        self.assertEqual(self._read_source(), original)
        self.assertEqual(self._leftover_files(), [])
        self.assertIn("Cookie 写回文件失败", "\n".join(captured.output))

    async def test_source_without_cookie_form_is_skipped(self):
        original = self._write_source(
            "curl 'https://weread.qq.com/web/book/read'"
        )
        session = self._session(
            [(self._cookie_response("new-key"), 0.01)],
            source_file=str(self.curl_file),
        )

        with self.assertLogs(level="WARNING") as captured:
            refreshed = await session._refresh_cookie()

        self.assertTrue(refreshed)
        self.assertEqual(self._read_source(), original)
        self.assertIn("未找到 Cookie 头或 -b 参数", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
