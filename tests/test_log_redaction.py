import asyncio
import io
import json
import logging
import sys
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

    def test_json_formatter_redacts_sensitive_message(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(self.bot.LogContextFilter())
        handler.setFormatter(self.bot.JsonLogFormatter())
        logger = logging.getLogger(f"redaction-test-{id(self)}")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)

        logger.error("request failed: token=unique-sensitive-token")

        payload = json.loads(stream.getvalue())
        self.assertNotIn("unique-sensitive-token", payload["message"])

    def test_json_formatter_redacts_json_shaped_secret(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(self.bot.LogContextFilter())
        handler.setFormatter(self.bot.JsonLogFormatter())
        logger = logging.getLogger(f"json-redaction-test-{id(self)}")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)

        logger.error(
            'request failed: {"token": "unique-json-secret", "ok": false}'
        )

        payload = json.loads(stream.getvalue())
        self.assertNotIn("unique-json-secret", payload["message"])

    def test_missing_identity_warning_does_not_echo_other_identity(self):
        session = object.__new__(self.bot.WeReadSessionManager)
        session.user_name = "alice"
        session.data = {
            "ps": "N/A",
            "pc": "unique-sensitive-pc",
            "appId": "safe-app-id",
        }

        with self.assertLogs(level=logging.WARNING) as captured:
            session._validate_and_log_user_identity()

        self.assertNotIn("unique-sensitive-pc", "\n".join(captured.output))

    def test_context_filter_does_not_mutate_shared_log_record(self):
        record = logging.LogRecord(
            name="shared-record",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request failed: token=%s",
            args=("unique-shared-secret",),
            exc_info=None,
        )

        self.bot.LogContextFilter().filter(record)

        self.assertEqual(record.msg, "request failed: token=%s")
        self.assertEqual(record.args, ("unique-shared-secret",))

    def test_text_formatter_ignores_unredacted_exception_cache(self):
        secret = "unique-exception-secret"
        try:
            raise RuntimeError(f"token={secret}")
        except RuntimeError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="cached-exception",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="request failed",
            args=(),
            exc_info=exc_info,
        )
        record.exc_text = "RuntimeError: token=unique-exception-secret"

        rendered = self.bot.RedactingLogFormatter("%(message)s").format(record)

        self.assertNotIn("unique-exception-secret", rendered)

    def test_curl_validation_does_not_echo_short_identity_values(self):
        with self.assertLogs(level=logging.ERROR):
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
