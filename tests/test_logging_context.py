import asyncio
import io
import logging
import unittest

from tests.helpers import load_weread_bot


class LoggingContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_tasks_keep_user_and_session_separate(self):
        bot = load_weread_bot()
        records = []

        class Collector(logging.Handler):
            def emit(self, record):
                records.append((record.getMessage(), record.user, record.session_id))

        handler = Collector()
        handler.addFilter(bot.LogContextFilter())
        logger = logging.getLogger(f"context-test-{id(self)}")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)

        async def worker(user, session_id):
            with bot.log_context(user, session_id):
                await asyncio.sleep(0)
                logger.info("event")

        await asyncio.gather(worker("alice", "s1"), worker("bob", "s2"))

        self.assertCountEqual(
            records,
            [("event", "alice", "s1"), ("event", "bob", "s2")],
        )

    def test_context_resets_to_system(self):
        bot = load_weread_bot()
        with bot.log_context("alice", "s1"):
            self.assertEqual(bot.CURRENT_USER.get(), "alice")
        self.assertEqual(bot.CURRENT_USER.get(), "system")
        self.assertEqual(bot.CURRENT_SESSION_ID.get(), "-")


if __name__ == "__main__":
    unittest.main()
