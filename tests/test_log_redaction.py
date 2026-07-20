import asyncio
import logging
import unittest
from unittest.mock import AsyncMock, patch

from tests.helpers import load_weread_bot


class LogRedactionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = load_weread_bot()

    def test_redacts_sensitive_mapping_and_cookie_text(self):
        secret_values = {
            "wr_skey": "skey-super-secret",
            "ps": "ps-super-secret",
            "pc": "pc-super-secret",
            "bot_token": "bot-super-secret",
            "webhook_url": "https://example.test/secret-hook",
        }
        redacted = self.bot.redact_for_log(secret_values)
        rendered = repr(redacted)
        for secret in secret_values.values():
            self.assertNotIn(secret, rendered)

        text = self.bot.redact_for_log(
            "Cookie: wr_skey=skey-super-secret; other=value"
        )
        self.assertNotIn("skey-super-secret", text)

    def test_curl_validation_does_not_echo_short_identity_values(self):
        errors = self.bot.CurlParser.validate_curl_headers(
            {"User-Agent": "Mozilla/5.0"},
            {"wr_skey": "long-enough-key"},
            {"appId": "x", "ps": "y", "pc": "z"},
            "alice",
        )[1]
        rendered = "\n".join(errors)
        self.assertNotIn("字段 appId 长度异常: x", rendered)
        self.assertNotIn("字段 ps 长度异常: y", rendered)
        self.assertNotIn("字段 pc 长度异常: z", rendered)

    async def test_http_retry_log_has_structured_fields_and_safe_url(self):
        bot = self.bot
        client = object.__new__(bot.HttpClient)
        client.config = bot.NetworkConfig(retry_times=2, retry_delay="0")
        client.request_times = []
        client._rate_limiter = unittest.mock.MagicMock()
        client._rate_limiter.acquire = AsyncMock()
        client._client = unittest.mock.MagicMock()
        client._client.post = AsyncMock(side_effect=[RuntimeError("boom"), RuntimeError("boom")])
        records = []

        class Collector(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Collector()
        logger = logging.getLogger()
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.WARNING)
        self.addCleanup(logger.removeHandler, handler)
        self.addCleanup(logger.setLevel, old_level)

        with self.assertRaises(RuntimeError):
            await client._request_with_retries(
                "https://example.test/path?token=secret"
            )

        retry_records = [r for r in records if getattr(r, "event", "") == "http_retry"]
        self.assertEqual(len(retry_records), 2)
        self.assertEqual(retry_records[0].attempt, 1)
        self.assertEqual(retry_records[0].max_attempts, 2)
        self.assertEqual(retry_records[0].error_category, "unknown")
        self.assertIsInstance(retry_records[0].elapsed_ms, int)
        self.assertNotIn("secret", retry_records[0].getMessage())


if __name__ == "__main__":
    unittest.main()
