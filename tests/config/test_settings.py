"""Settings tests."""

from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError

from claude_telegram.config.settings import AppSettings
from claude_telegram.domain.models import ClaudeEffort, ClaudeModel
from tests.test_support import configured_settings


class AppSettingsTests(TestCase):
    def test_parses_allowed_user_ids_and_defaults(self) -> None:
        with configured_settings() as settings:
            self.assertEqual(settings.allowed_user_ids, frozenset({1, 2}))
            self.assertEqual(settings.default_model, ClaudeModel.SONNET)
            self.assertEqual(settings.default_effort, ClaudeEffort.HIGH)

    def test_requires_non_empty_bot_token(self) -> None:
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": ""}, clear=True):
            with self.assertRaises(ValidationError):
                AppSettings()

