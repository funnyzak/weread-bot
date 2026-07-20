import unittest
from unittest.mock import AsyncMock

from tests.helpers import FakeClock, FakeHttpClient, load_weread_bot


class FakeBehavior:
    def should_take_break(self):
        return False

    def get_reading_interval(self, _value):
        return 0


class FakeNotification:
    def __init__(self):
        self.events = []

    async def send_notification_async(self, message, event):
        self.events.append(event)
        return True


class SessionLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = load_weread_bot()
        self.cancelled = False

    def _manager(self, outcomes, clock, target="1"):
        manager = object.__new__(self.bot.WeReadSessionManager)
        manager.user_config = None
        manager.user_name = "default"
        manager._is_cancelled = lambda: self.cancelled
        manager.config = self.bot.WeReadConfig(
            startup_delay="0",
            notification=self.bot.NotificationConfig(
                enabled=True, include_statistics=True
            ),
        )
        manager.effective_reading_config = self.bot.ReadingConfig(
            target_duration=target,
            reading_interval="0",
            max_consecutive_failures=5,
        )
        manager.session_stats = self.bot.ReadingSession(user_name="default")
        manager.behavior_simulator = FakeBehavior()
        manager.notification_service = FakeNotification()
        manager.http_client = FakeHttpClient()
        manager._refresh_cookie = AsyncMock(return_value=True)

        async def simulate(_last_time):
            outcome = outcomes.pop(0)
            if callable(outcome):
                return outcome()
            return outcome, 0.01

        manager._simulate_reading_request = simulate

        async def fake_sleep(seconds, is_cancelled):
            if is_cancelled():
                return False
            clock.advance(max(float(seconds), 0.01))
            return not is_cancelled()

        manager._monotonic = clock.monotonic
        self.bot.interruptible_sleep = fake_sleep
        return manager

    async def test_five_consecutive_failures_end_session_as_failed(self):
        manager = self._manager([False] * 5, FakeClock())

        result = await manager.start_reading_session()

        self.assertEqual(result.status, self.bot.SessionStatus.FAILED)
        self.assertEqual(result.stats.failed_reads, 5)
        self.assertEqual(manager.http_client.close_calls, 1)

    async def test_success_resets_consecutive_failure_count(self):
        clock = FakeClock()

        def successful_read():
            clock.advance(60)
            return True, 0.01

        manager = self._manager(
            [False, False, successful_read], clock
        )

        result = await manager.start_reading_session()

        self.assertEqual(result.status, self.bot.SessionStatus.SUCCESS)
        self.assertEqual(result.stats.successful_reads, 1)
        self.assertEqual(result.stats.failed_reads, 2)

    async def test_deadline_without_success_is_failed(self):
        clock = FakeClock()

        def failed_read():
            clock.advance(60)
            return False, 0.01

        manager = self._manager([failed_read], clock)

        result = await manager.start_reading_session()

        self.assertEqual(result.status, self.bot.SessionStatus.FAILED)
        self.assertEqual(result.stats.successful_reads, 0)

    async def test_shutdown_is_cancelled_without_success_notification(self):
        clock = FakeClock()
        manager = self._manager([], clock)
        self.cancelled = True

        result = await manager.start_reading_session()

        self.assertEqual(result.status, self.bot.SessionStatus.CANCELLED)
        self.assertEqual(manager.notification_service.events, [])
        self.assertEqual(manager.http_client.close_calls, 1)

    async def test_auth_failure_sends_failure_notification_and_closes(self):
        manager = self._manager([], FakeClock())
        manager._refresh_cookie = AsyncMock(return_value=False)

        result = await manager.start_reading_session()

        self.assertEqual(result.status, self.bot.SessionStatus.FAILED)
        self.assertEqual(
            manager.notification_service.events,
            [self.bot.NotificationEvent.SESSION_FAILURE],
        )
        self.assertEqual(manager.http_client.close_calls, 1)

    async def test_network_failures_keep_network_error_category(self):
        def network_failure():
            raise TimeoutError("offline")

        manager = self._manager([network_failure] * 5, FakeClock())

        with self.assertLogs(level="ERROR"):
            result = await manager.start_reading_session()

        self.assertEqual(result.status, self.bot.SessionStatus.FAILED)
        self.assertEqual(
            result.error_category,
            self.bot.RuntimeErrorCategory.NETWORK,
        )

    async def test_shutdown_during_cookie_refresh_is_cancelled(self):
        clock = FakeClock()
        manager = self._manager([], clock)

        async def refresh_cookie():
            clock.advance(7)
            self.cancelled = True
            return False

        manager._refresh_cookie = refresh_cookie

        result = await manager.start_reading_session()

        self.assertEqual(result.status, self.bot.SessionStatus.CANCELLED)
        self.assertEqual(result.stats.actual_duration_seconds, 7)
        self.assertEqual(manager.notification_service.events, [])

    async def test_shutdown_during_fifth_failure_wins_over_failure_limit(self):
        def final_failure():
            self.cancelled = True
            return False, 0.01

        manager = self._manager(
            [False, False, False, False, final_failure],
            FakeClock(),
        )

        result = await manager.start_reading_session()

        self.assertEqual(result.status, self.bot.SessionStatus.CANCELLED)
        self.assertEqual(manager.notification_service.events, [])

    async def test_fractional_target_duration_is_not_truncated_to_zero(self):
        clock = FakeClock()

        def successful_read():
            clock.advance(30)
            return True, 0.01

        manager = self._manager([successful_read], clock, target="0.5")

        result = await manager.start_reading_session()

        self.assertEqual(result.status, self.bot.SessionStatus.SUCCESS)
        self.assertEqual(result.stats.actual_duration_seconds, 30)

    async def test_progress_log_limits_target_minutes_to_two_decimals(self):
        clock = FakeClock()

        def successful_read():
            clock.advance(2.2841002174537737 * 60)
            return True, 0.01

        manager = self._manager(
            [successful_read],
            clock,
            target="2.2841002174537737",
        )

        with self.assertLogs(level="INFO") as captured:
            result = await manager.start_reading_session()

        self.assertEqual(result.status, self.bot.SessionStatus.SUCCESS)
        self.assertIn(
            "✅ 阅读成功，进度: 2分钟 / 2.28分钟",
            "\n".join(captured.output),
        )


if __name__ == "__main__":
    unittest.main()
