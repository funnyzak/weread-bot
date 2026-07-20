import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.helpers import load_weread_bot


class ConfigValidationTests(unittest.TestCase):
    def setUp(self):
        self.bot = load_weread_bot()

    def _config_file(self, text):
        temp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        temp.write(text)
        temp.close()
        self.addCleanup(lambda: Path(temp.name).unlink(missing_ok=True))
        return temp.name

    def test_yaml_string_false_is_false(self):
        path = self._config_file(
            "notification:\n  triggers:\n    session_success: \"false\"\n"
        )
        config = self.bot.ConfigManager(path).config
        self.assertFalse(
            config.notification.triggers[
                self.bot.NotificationEvent.SESSION_SUCCESS
            ]
        )

    def test_yaml_syntax_error_raises_config_error(self):
        path = self._config_file("reading: [unterminated\n")
        with self.assertRaises(self.bot.ConfigError):
            self.bot.ConfigManager(path)

    def test_boolean_parser_accepts_known_values_and_rejects_other_text(self):
        for value in (True, "TRUE", "false", "1", "0", "yes", "No", "on", "OFF"):
            with self.subTest(value=value):
                self.assertIsInstance(self.bot.parse_bool(value, "x.y"), bool)
        with self.assertRaisesRegex(self.bot.ConfigError, "x.y"):
            self.bot.parse_bool("sometimes", "x.y")

    def test_unresolved_environment_placeholder_reports_path(self):
        path = self._config_file("curl_config:\n  content: ${MISSING_FOR_TEST}\n")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MISSING_FOR_TEST", None)
            with self.assertRaisesRegex(self.bot.ConfigError, "curl_config.content"):
                self.bot.ConfigManager(path)

    def test_nested_unresolved_placeholder_reports_exact_path(self):
        path = self._config_file(
            "notification:\n"
            "  channels:\n"
            "    - name: feishu\n"
            "      config:\n"
            "        webhook_url: ${MISSING_NESTED_FOR_TEST}\n"
        )
        os.environ.pop("MISSING_NESTED_FOR_TEST", None)
        with self.assertRaisesRegex(
            self.bot.ConfigError,
            r"notification.channels\[0\].config.webhook_url",
        ):
            self.bot.ConfigManager(path)

    def test_runtime_semantic_boundaries(self):
        cases = []

        config = self.bot.WeReadConfig(max_concurrent_users=0)
        cases.append((config, "app.max_concurrent_users"))
        config = self.bot.WeReadConfig()
        config.reading.max_consecutive_failures = 0
        cases.append((config, "reading.max_consecutive_failures"))
        config = self.bot.WeReadConfig()
        config.network.timeout = 0
        cases.append((config, "network.timeout"))
        config = self.bot.WeReadConfig()
        config.network.retry_times = 0
        cases.append((config, "network.retry_times"))
        config = self.bot.WeReadConfig()
        config.network.rate_limit = -1
        cases.append((config, "network.rate_limit"))
        config = self.bot.WeReadConfig()
        config.daemon.max_daily_sessions = 0
        cases.append((config, "daemon.max_daily_sessions"))
        config = self.bot.WeReadConfig()
        config.human_simulation.break_probability = -0.1
        cases.append((config, "human_simulation.break_probability"))

        for config, path_name in cases:
            with self.subTest(path=path_name):
                with self.assertRaisesRegex(self.bot.ConfigError, path_name):
                    self.bot.validate_config_semantics(config)

    def test_persistent_modes_require_enabled_sections(self):
        scheduled = self.bot.WeReadConfig(startup_mode="scheduled")
        daemon = self.bot.WeReadConfig(startup_mode="daemon")
        with self.assertRaisesRegex(self.bot.ConfigError, "schedule.enabled"):
            self.bot._validate_runtime_config(scheduled)
        with self.assertRaisesRegex(self.bot.ConfigError, "daemon.enabled"):
            self.bot._validate_runtime_config(daemon)

    def test_cli_can_override_persistent_mode_before_runtime_validation(self):
        path = self._config_file(
            "app:\n  startup_mode: scheduled\n"
            "schedule:\n  enabled: false\n"
        )

        config = self.bot.ConfigManager(path).config

        self.assertEqual(config.startup_mode, "scheduled")

    def test_curl_source_prefers_existing_file_and_falls_back_to_inline(self):
        curl_path = self._config_file("file-curl")
        self.assertEqual(
            self.bot.load_curl_source(curl_path, "inline-curl", "curl_config"),
            "file-curl",
        )
        self.assertEqual(
            self.bot.load_curl_source(
                "/missing/curl.txt", "inline-curl", "curl_config"
            ),
            "inline-curl",
        )

    def test_notification_environment_mapping_is_shared(self):
        manager = object.__new__(self.bot.ConfigManager)
        with patch.dict(
            os.environ,
            {
                "PUSHPLUS_TOKEN": "fake-pushplus-token",
                "GOTIFY_SERVER": "https://gotify.test",
                "GOTIFY_TOKEN": "fake-gotify-token",
                "GOTIFY_PRIORITY": "3",
            },
        ):
            channels = manager._create_channels_from_env_vars()
            gotify_override = manager._apply_env_overrides_to_channel(
                "gotify", {"title": "yaml-title"}
            )

        by_name = {channel.name: channel for channel in channels}
        self.assertEqual(
            by_name["pushplus"].config["token"], "fake-pushplus-token"
        )
        self.assertEqual(gotify_override["priority"], 3)
        self.assertEqual(gotify_override["title"], "yaml-title")

    def test_chapter_index_zero_is_preserved(self):
        path = self._config_file(
            "reading:\n"
            "  books:\n"
            "    - name: Book\n"
            "      book_id: b\n"
            "      chapters:\n"
            "        - chapter_id: c\n"
            "          chapter_index: 0\n"
        )
        config = self.bot.ConfigManager(path).config
        self.assertEqual(config.reading.books[0].chapter_infos[0].chapter_index, 0)

    def test_numeric_and_range_parsers_enforce_bounds(self):
        self.assertEqual(self.bot.parse_int("2", "network.retry_times", 1), 2)
        self.assertEqual(
            self.bot.parse_float("0.5", "human.break_probability", 0, 1),
            0.5,
        )
        self.assertEqual(
            self.bot.parse_range("0-2", "reading.interval", 0),
            (0.0, 2.0),
        )
        with self.assertRaisesRegex(self.bot.ConfigError, "network.timeout"):
            self.bot.parse_int(0, "network.timeout", minimum=1)
        with self.assertRaisesRegex(self.bot.ConfigError, "reading.target_duration"):
            self.bot.parse_range("0-1", "reading.target_duration", minimum=0.000001)
        with self.assertRaisesRegex(self.bot.ConfigError, "probability"):
            self.bot.parse_float(1.1, "probability", minimum=0, maximum=1)

    def test_invalid_modes_and_logging_values_fail_during_load(self):
        cases = [
            ("app:\n  startup_mode: once\n", "app.startup_mode", "STARTUP_MODE", "once"),
            ("reading:\n  mode: chaos\n", "reading.mode", "READING_MODE", "chaos"),
            ("logging:\n  level: TRACE\n", "logging.level", "LOG_LEVEL", "TRACE"),
            ("logging:\n  format: xml\n", "logging.format", "LOG_FORMAT", "xml"),
        ]
        for text, path_name, env_key, env_value in cases:
            with self.subTest(path=path_name):
                with patch.dict(os.environ, {env_key: env_value}):
                    with self.assertRaisesRegex(self.bot.ConfigError, path_name):
                        self.bot.ConfigManager(self._config_file(text))

    def test_user_overrides_use_same_validation(self):
        path = self._config_file(
            "curl_config:\n"
            "  users:\n"
            "    - name: alice\n"
            "      content: safe-placeholder\n"
            "      reading_overrides:\n"
            "        mode: invalid\n"
        )
        with self.assertRaisesRegex(
            self.bot.ConfigError,
            r"curl_config.users\[0\].reading_overrides.mode",
        ):
            self.bot.ConfigManager(path)


if __name__ == "__main__":
    unittest.main()
