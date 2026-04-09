"""Custom long-polling runner."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

from claude_telegram.config.settings import AppSettings
from claude_telegram.persistence.repositories import UpdateRepository

log = logging.getLogger(__name__)


class TelegramPollingRunner:
    """Feed updates into aiogram while controlling offset persistence."""

    def __init__(
        self,
        bot: Bot,
        dispatcher: Dispatcher,
        settings: AppSettings,
        update_repository: UpdateRepository,
    ):
        self._bot = bot
        self._dispatcher = dispatcher
        self._settings = settings
        self._update_repository = update_repository

    async def run(self) -> None:
        offset = await self._update_repository.next_offset()
        while True:
            try:
                updates = await self._bot.get_updates(
                    offset=offset,
                    timeout=self._settings.poll_timeout_seconds,
                    allowed_updates=["message"],
                )
            except asyncio.CancelledError:
                raise
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
                continue
            except TelegramNetworkError:
                log.warning("Telegram polling failed; retrying.", exc_info=True)
                await asyncio.sleep(5)
                continue

            for update in updates:
                if await self._update_repository.is_processed(update.update_id):
                    offset = update.update_id + 1
                    continue
                await self._dispatcher.feed_update(self._bot, update)
                await self._update_repository.mark_processed(update.update_id)
                offset = update.update_id + 1

