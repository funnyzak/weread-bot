import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from tests.helpers import load_weread_bot


VALID_CURL = (
    "curl 'https://weread.qq.com/web/book/read' "
    "-H 'accept: application/json' "
    "-H 'Cookie: wr_skey=oldkey12345; wr_vid=12345678' "
    "-H 'user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)' "
    "--data-raw '{\"appId\":\"wb1234567890\",\"ps\":\"ps1234567\","
    "\"pc\":\"pc1234567\"}'"
)


class CurlSourceTrackingTests(unittest.TestCase):
    """CURL 来源是文件还是内嵌内容的判定。"""

    def setUp(self):
        self.bot = load_weread_bot()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.temp_dir = Path(temp_dir.name)

    def test_file_source_reports_path_and_content(self):
        source = self.temp_dir / "curl_command.txt"
        source.write_text(VALID_CURL + "\n", encoding="utf-8")

        content, origin = self.bot.load_curl_source_with_origin(
            str(source), "", "curl_config"
        )

        self.assertEqual(content, VALID_CURL)
        self.assertEqual(origin, str(source))

    def test_inline_source_has_no_file_origin(self):
        content, origin = self.bot.load_curl_source_with_origin(
            "", VALID_CURL, "curl_config"
        )

        self.assertEqual(content, VALID_CURL)
        self.assertIsNone(origin)

    def test_empty_file_reports_no_origin_and_no_fallback(self):
        source = self.temp_dir / "curl_command.txt"
        source.write_text("  \n", encoding="utf-8")

        content, origin = self.bot.load_curl_source_with_origin(
            str(source), VALID_CURL, "curl_config"
        )

        self.assertEqual(content, "")
        self.assertIsNone(origin)

    def _load_session(self, config, user_config=None):
        session = object.__new__(self.bot.WeReadSessionManager)
        session.config = config
        session.user_config = user_config
        session.user_name = user_config.name if user_config else "default"
        session.data = self.bot.WeReadSessionManager.DEFAULT_DATA.copy()
        session.reading_manager = MagicMock()
        session.reading_manager.set_curl_data.return_value = True
        session.headers = {}
        session.cookies = {}
        session._curl_source_file = None
        session._load_curl_config()
        return session

    def test_session_records_global_curl_file(self):
        source = self.temp_dir / "curl_command.txt"
        source.write_text(VALID_CURL, encoding="utf-8")

        session = self._load_session(
            self.bot.WeReadConfig(curl_file_path=str(source))
        )

        self.assertEqual(session._curl_source_file, str(source))
        self.assertEqual(session.cookies["wr_skey"], "oldkey12345")

    def test_session_records_user_curl_file_over_global(self):
        user_source = self.temp_dir / "user.txt"
        user_source.write_text(VALID_CURL, encoding="utf-8")
        global_source = self.temp_dir / "global.txt"
        global_source.write_text(VALID_CURL, encoding="utf-8")

        session = self._load_session(
            self.bot.WeReadConfig(curl_file_path=str(global_source)),
            self.bot.UserConfig(name="alice", file_path=str(user_source)),
        )

        self.assertEqual(session._curl_source_file, str(user_source))

    def test_session_without_file_source_records_none(self):
        session = self._load_session(
            self.bot.WeReadConfig(curl_content=VALID_CURL)
        )

        self.assertIsNone(session._curl_source_file)
        self.assertEqual(session.cookies["wr_skey"], "oldkey12345")


if __name__ == "__main__":
    unittest.main()
