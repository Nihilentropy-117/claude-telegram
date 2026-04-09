"""Aiogram middleware."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

log = logging.getLogger(__name__)


class AuthorizationMiddleware(BaseMiddleware):
    """Ignore messages from users outside the configured allowlist."""

    def __init__(self, allowed_user_ids: frozenset[int]):
        self._allowed_user_ids = allowed_user_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self._allowed_user_ids:
            return await handler(event, data)
        event_from_user = data.get("event_from_user")
        if event_from_user is not None and event_from_user.id in self._allowed_user_ids:
            return await handler(event, data)
        if event_from_user is not None:
            log.warning("Unauthorized Telegram user %s attempted to use the bot.", event_from_user.id)
        return None

