import unittest
import signal
from argparse import Namespace
from unittest.mock import AsyncMock, patch

from tests.helpers import load_weread_bot


class ApplicationResultTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = load_weread_bot()

    def test_run_result_status_and_exit_codes(self):
        success = self.bot.RunResult(final_status="success", user_count=1)
        partial = self.bot.RunResult(
            final_status="partial_success",
            user_count=2,
            successful_users=1,
            failed_users=1,
        )
        failed = self.bot.RunResult(
            final_status="failed", user_count=1, failed_users=1
        )
        cancelled = self.bot.RunResult(
            final_status="cancelled", user_count=1, cancelled_users=1
        )

        self.assertEqual(success.exit_code, 0)
        self.assertEqual(partial.exit_code, 1)
        self.assertEqual(failed.exit_code, 1)
        self.assertEqual(cancelled.exit_code, 1)
        self.assertEqual(partial.to_summary_dict()["final_status"], "partial_success")
        self.assertEqual(cancelled.to_summary_dict()["cancelled_users"], 1)

    def test_aggregate_session_results(self):
        stats = self.bot.ReadingSession(successful_reads=1)
        results = [
            self.bot.SessionResult(self.bot.SessionStatus.SUCCESS, stats),
            self.bot.SessionResult(
                self.bot.SessionStatus.FAILED,
                self.bot.ReadingSession(failed_reads=1),
                self.bot.RuntimeErrorCategory.NETWORK,
                "network failed",
            ),
        ]

        result = self.bot.RunResult.from_session_results(results)

        self.assertEqual(result.final_status, "partial_success")
        self.assertEqual(result.successful_users, 1)
        self.assertEqual(result.failed_users, 1)
        self.assertEqual(result.failure_categories, {"network": 1})

    async def test_single_user_failed_session_is_not_success(self):
        config = self.bot.WeReadConfig()
        app = object.__new__(self.bot.WeReadApplication)
        app.config = config
        self.bot.WeReadApplication._instance = app
        session_result = self.bot.SessionResult(
            self.bot.SessionStatus.FAILED,
            self.bot.ReadingSession(user_name="default", failed_reads=5),
            self.bot.RuntimeErrorCategory.PROTOCOL,
            "too many failures",
        )
        fake_manager = unittest.mock.MagicMock()
        fake_manager.start_reading_session = AsyncMock(return_value=session_result)

        with patch.object(self.bot, "WeReadSessionManager", return_value=fake_manager):
            result = await self.bot.WeReadApplication._run_single_user_session(app)

        self.assertEqual(result.final_status, "failed")
        self.assertEqual(result.exit_code, 1)

    async def test_main_returns_run_result_exit_code(self):
        config = self.bot.WeReadConfig(curl_content="safe")
        args = Namespace(
            mode=None,
            config="unused.yaml",
            verbose=False,
            validate_config=False,
            dry_run=False,
            show_last_run=False,
        )
        fake_app = unittest.mock.MagicMock()
        fake_app.run = AsyncMock(
            return_value=self.bot.RunResult(
                final_status="failed", user_count=1, failed_users=1
            )
        )
        with (
            patch.object(self.bot, "parse_arguments", return_value=args),
            patch.object(
                self.bot,
                "ConfigManager",
                return_value=unittest.mock.MagicMock(config=config),
            ),
            patch.object(self.bot, "setup_logging"),
            patch.object(self.bot, "_validate_runtime_config"),
            patch.object(self.bot, "_validate_curl_configs", new=AsyncMock()),
            patch.object(self.bot, "WeReadApplication", return_value=fake_app),
            patch.object(self.bot, "requests", object()),
            patch.object(self.bot, "httpx", object()),
        ):
            exit_code = await self.bot.main()

        self.assertEqual(exit_code, 1)

    async def test_main_returns_130_for_keyboard_interrupt(self):
        config = self.bot.WeReadConfig(curl_content="safe")
        args = Namespace(
            mode=None,
            config="unused.yaml",
            verbose=False,
            validate_config=False,
            dry_run=False,
            show_last_run=False,
        )
        fake_app = unittest.mock.MagicMock()
        fake_app.run = AsyncMock(side_effect=KeyboardInterrupt)
        with (
            patch.object(self.bot, "parse_arguments", return_value=args),
            patch.object(
                self.bot,
                "ConfigManager",
                return_value=unittest.mock.MagicMock(config=config),
            ),
            patch.object(self.bot, "setup_logging"),
            patch.object(self.bot, "_validate_runtime_config"),
            patch.object(self.bot, "_validate_curl_configs", new=AsyncMock()),
            patch.object(self.bot, "WeReadApplication", return_value=fake_app),
            patch.object(self.bot, "requests", object()),
            patch.object(self.bot, "httpx", object()),
        ):
            exit_code = await self.bot.main()

        self.assertEqual(exit_code, 130)

    def test_signal_requests_shutdown_and_records_interrupt(self):
        with patch.object(self.bot.signal, "signal"):
            app = self.bot.WeReadApplication(self.bot.WeReadConfig())

        app._signal_handler(signal.SIGINT, None)

        self.assertTrue(app.is_shutdown_requested())
        self.assertEqual(app.shutdown_signal, signal.SIGINT)

    def test_application_shutdown_state_is_isolated_per_instance(self):
        with patch.object(self.bot.signal, "signal"):
            first = self.bot.WeReadApplication(self.bot.WeReadConfig())
            second = self.bot.WeReadApplication(self.bot.WeReadConfig())

        first._signal_handler(signal.SIGTERM, None)

        self.assertTrue(first.is_shutdown_requested())
        self.assertFalse(second.is_shutdown_requested())


if __name__ == "__main__":
    unittest.main()
