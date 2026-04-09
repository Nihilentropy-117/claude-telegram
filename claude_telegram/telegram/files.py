"""Outbox file delivery: send files from /temp/outbox/ to Telegram."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_telegram.telegram.client import TelegramClient

log = logging.getLogger(__name__)

OUTBOX_DIR = Path("/temp/outbox")

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".avi", ".mov", ".mkv", ".webm"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".ogg", ".wav", ".flac", ".m4a", ".aac"})


async def deliver_outbox(telegram: TelegramClient, chat_id: int) -> None:
    """Send every file in the outbox directory, then delete each on success."""
    if not OUTBOX_DIR.exists():
        return

    for file in sorted(OUTBOX_DIR.iterdir()):
        if not file.is_file():
            continue

        extension = file.suffix.lower()
        path_str = str(file)

        try:
            if extension in IMAGE_EXTENSIONS:
                result = await telegram.send_photo(chat_id, path_str)
            elif extension in VIDEO_EXTENSIONS:
                result = await telegram.send_video(chat_id, path_str)
            elif extension in AUDIO_EXTENSIONS:
                result = await telegram.send_audio(chat_id, path_str)
            else:
                result = await telegram.send_document(chat_id, path_str)

            if result.get("ok"):
                file.unlink()
                log.info("Delivered outbox file: %s", file.name)
            else:
                log.error("Failed to deliver %s: %s", file.name, result)

        except Exception as exc:
            log.error("Error delivering outbox file %s: %s", file.name, exc)
