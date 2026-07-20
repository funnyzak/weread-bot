import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tests.helpers import load_weread_bot


class RunHistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = load_weread_bot()

    async def test_run_single_session_persists_exactly_once(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        config = self.bot.WeReadConfig(
            history=self.bot.HistoryConfig(
                enabled=True,
                file=str(Path(temp_dir.name) / "history.json"),
            )
        )
        app = object.__new__(self.bot.WeReadApplication)
        app.config = config
        app.execution_type = "normal"
        self.bot.WeReadApplication._instance = app
        result = self.bot.RunResult(
            final_status="failed", user_count=1, failed_users=1
        )

        with patch.object(
            self.bot.WeReadApplication,
            "_run_single_user_session",
            new=AsyncMock(return_value=result),
        ):
            returned = await self.bot.WeReadApplication.run_single_session()

        history = self.bot.load_run_history(config.history.file)
        self.assertIs(returned, result)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["final_status"], "failed")

    def test_cancelled_status_is_preserved_in_history(self):
        config = self.bot.WeReadConfig()
        result = self.bot.RunResult(
            final_status="cancelled",
            user_count=1,
            cancelled_users=1,
        )

        record = self.bot.build_run_history_record(
            config, "normal", result.to_summary_dict()
        )

        self.assertEqual(record["final_status"], "cancelled")
        self.assertEqual(record["cancelled_users"], 1)


if __name__ == "__main__":
    unittest.main()
