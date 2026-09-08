import unittest
from unittest.mock import AsyncMock, patch

from tests.helpers import FakeHttpClient, load_weread_bot


class ProtocolStateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = load_weread_bot()

    def _reading_config(self):
        return self.bot.ReadingConfig(
            mode="pure_random",
            books=[
                self.bot.BookInfo(
                    name="Book A",
                    book_id="a",
                    chapters=["a0", "a1"],
                    chapter_infos=[
                        self.bot.ChapterInfo("a0", 0),
                        self.bot.ChapterInfo("a1", 11),
                    ],
                ),
                self.bot.BookInfo(
                    name="Book B",
                    book_id="b",
                    chapters=["b0"],
                    chapter_infos=[self.bot.ChapterInfo("b0", 20)],
                ),
            ],
        )

    def test_only_truthy_succ_and_synckey_is_success(self):
        cases = [
            ({"succ": True, "synckey": "key"}, True),
            ({"succ": False, "synckey": "key"}, False),
            ({"succ": 0, "synckey": "key"}, False),
            ({"synckey": "key"}, False),
            ({"succ": True, "synckey": ""}, False),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.bot.is_successful_read_response(payload), expected
                )

    def test_pure_random_updates_complete_position_including_ci(self):
        manager = self.bot.SmartReadingManager(self._reading_config())
        with patch.object(self.bot.random, "choice", side_effect=["b", "b0"]):
            self.assertEqual(manager._pure_random_position(), ("b", "b0"))

        self.assertEqual(manager.current_book_id, "b")
        self.assertEqual(manager.current_book_name, "Book B")
        self.assertEqual(manager.current_book_chapters, ["b0"])
        self.assertEqual(manager.current_chapter_index, 0)
        self.assertEqual(manager.current_chapter_ci, 20)

    def test_curl_without_position_keeps_identity_then_falls_back(self):
        session = object.__new__(self.bot.WeReadSessionManager)
        session.user_name = "alice"
        session.data = self.bot.WeReadSessionManager.DEFAULT_DATA.copy()
        session.reading_manager = unittest.mock.MagicMock()
        session.reading_manager.set_curl_data.return_value = True

        session._apply_curl_payload({"appId": "app", "ps": "ps1", "pc": "pc1"})

        self.assertEqual(session.user_app_id, "app")
        self.assertEqual(session.user_ps, "ps1")
        self.assertEqual(session.user_pc, "pc1")
        session.reading_manager.set_curl_data.assert_called_once_with("", "")

    def test_protocol_position_fails_when_no_position_can_be_initialized(self):
        session = object.__new__(self.bot.WeReadSessionManager)
        session.user_name = "alice"
        session.reading_manager = unittest.mock.MagicMock()
        session.reading_manager.set_curl_data.return_value = False

        with self.assertRaisesRegex(ValueError, "阅读位置初始化失败"):
            session._apply_protocol_reading_position("book", "chapter", 1)

    def test_prepare_payload_removes_stale_ci(self):
        session = object.__new__(self.bot.WeReadSessionManager)
        session.data = self.bot.WeReadSessionManager.DEFAULT_DATA.copy()
        session.data["ci"] = 99
        session.reading_manager = unittest.mock.MagicMock()
        session.reading_manager.get_next_reading_position.return_value = ("book", "chapter")
        session.reading_manager.current_chapter_ci = None
        session._apply_user_identity_to_payload = unittest.mock.MagicMock()

        session._prepare_read_payload(1)

        self.assertNotIn("ci", session.data)

    async def test_synckey_fix_uses_current_book(self):
        session = object.__new__(self.bot.WeReadSessionManager)
        session.http_client = FakeHttpClient()
        session.headers = {}
        session.cookies = {}
        session.data = {"b": "current-book"}
        session.user_name = "alice"

        await session._fix_no_synckey()

        self.assertEqual(
            session.http_client.raw_calls[0]["json_data"],
            {"bookIds": ["current-book"]},
        )


if __name__ == "__main__":
    unittest.main()
