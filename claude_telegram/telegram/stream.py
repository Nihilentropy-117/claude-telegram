"""StreamBridge: throttled streaming of text to Telegram via sendMessageDraft."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_telegram.telegram.client import TelegramClient

MAX_MESSAGE_LENGTH = 4096


class StreamBridge:
    """Buffers text chunks and streams them to a Telegram chat via drafts.

    Text is pushed as drafts at a throttled interval to avoid rate limits,
    then finalized as a permanent message once the response is complete.
    """

    def __init__(
        self,
        telegram: TelegramClient,
        chat_id: int,
        interval_seconds: float,
    ) -> None:
        self._telegram = telegram
        self._chat_id = chat_id
        # Random signed-int64 draft ID for sendMessageDraft
        self._draft_id = int.from_bytes(os.urandom(8), "big") >> 1 or 1
        self._buffer = ""
        self._last_push = 0.0
        self._interval = interval_seconds

    async def push(self, chunk: str) -> None:
        """Append text and flush a draft update if the throttle interval has elapsed."""
        self._buffer += chunk
        if time.monotonic() - self._last_push >= self._interval:
            await self._flush_draft()

    async def _flush_draft(self) -> None:
        if not self._buffer.strip():
            return
        # Only send the tail when buffer exceeds Telegram's message limit
        visible = self._buffer[-MAX_MESSAGE_LENGTH:]
        await self._telegram.send_draft(self._chat_id, self._draft_id, visible)
        self._last_push = time.monotonic()

    async def finalize(self, full_text: str) -> None:
        """Send the complete text as permanent message(s), replacing the draft."""
        if not full_text.strip():
            full_text = "_(empty response)_"
        for chunk in split_text(full_text, MAX_MESSAGE_LENGTH):
            await self._telegram.send_message(self._chat_id, chunk)


def split_text(text: str, max_length: int) -> list[str]:
    """Split text into chunks that fit within max_length, preferring newline boundaries."""
    if len(text) <= max_length:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, max_length)
        if cut == -1 or cut < max_length // 2:
            cut = max_length
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks
