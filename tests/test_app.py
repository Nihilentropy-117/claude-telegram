"""Application wiring smoke test."""

from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from claude_telegram.app import ClaudeTelegramApplication
from tests.test_support import configured_settings


class ApplicationSmokeTests(IsolatedAsyncioTestCase):
    async def test_application_can_be_created_and_closed(self) -> None:
        with configured_settings() as settings:
            application = await ClaudeTelegramApplication.create(settings)
            try:
                self.assertEqual(application.settings.telegram_bot_token, "123456:TESTTOKEN")
            finally:
                await application.close()
