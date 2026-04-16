"""Extract prompts from Telegram messages.

Handles text, captions, files (document, photo, voice, audio, video),
locations, and contacts. Files are downloaded to a temp directory.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_telegram.telegram.client import TelegramClient

log = logging.getLogger(__name__)

TEMP_DIR = Path("/temp")


async def extract_prompt(
    message: dict, telegram: TelegramClient,
) -> str | None:
    """Parse a Telegram message into a prompt string for Claude.

    Downloads any attached files to TEMP_DIR. Returns None if the
    message has no usable content.
    """
    parts: list[str] = []

    user_text = message.get("caption") or message.get("text", "")
    if user_text:
        parts.append(user_text)

    file_info = _extract_file_info(message)
    if file_info:
        file_id, file_name, description = file_info
        download_note = await _download_file(
            file_id, file_name, description, telegram,
        )
        parts.append(download_note)

    if "location" in message:
        loc = message["location"]
        parts.append(
            f"[User shared a location: {loc['latitude']}, {loc['longitude']}]"
        )

    if "contact" in message:
        contact = message["contact"]
        name = (
            f"{contact.get('first_name', '')} {contact.get('last_name', '')}"
        ).strip()
        phone = contact.get("phone_number", "unknown")
        parts.append(f"[User shared a contact: {name}, phone: {phone}]")

    return "\n".join(parts) if parts else None


def _extract_file_info(message: dict) -> tuple[str, str, str] | None:
    """Extract (file_id, file_name, description) from a file-bearing message."""
    if "document" in message:
        doc = message["document"]
        return (
            doc["file_id"],
            doc.get("file_name", f"document_{doc['file_id'][:8]}"),
            f"document ({doc.get('mime_type', 'unknown type')})",
        )

    if "photo" in message:
        photo = message["photo"][-1]  # Telegram sends multiple sizes; pick largest
        return (
            photo["file_id"],
            f"photo_{photo['file_id'][:8]}.jpg",
            f"photo ({photo.get('width', '?')}x{photo.get('height', '?')})",
        )

    if "voice" in message:
        voice = message["voice"]
        return (
            voice["file_id"],
            f"voice_{voice['file_id'][:8]}.ogg",
            f"voice message ({voice.get('duration', '?')}s)",
        )

    if "audio" in message:
        audio = message["audio"]
        performer = audio.get("performer", "")
        title = audio.get("title", "")
        label = (
            f"{performer} - {title}".strip(" -") if (performer or title) else ""
        )
        name = audio.get("file_name", f"audio_{audio['file_id'][:8]}.mp3")
        desc = f"audio file: {label or name} ({audio.get('duration', '?')}s)"
        return (audio["file_id"], name, desc)

    if "video" in message:
        video = message["video"]
        return (
            video["file_id"],
            video.get("file_name", f"video_{video['file_id'][:8]}.mp4"),
            f"video ({video.get('width', '?')}x{video.get('height', '?')}, "
            f"{video.get('duration', '?')}s)",
        )

    return None


async def _download_file(
    file_id: str,
    file_name: str,
    description: str,
    telegram: TelegramClient,
) -> str:
    """Download a Telegram file to TEMP_DIR. Returns a bracketed status note."""
    try:
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        result = await telegram.get_file(file_id)
        telegram_path = result.get("result", {}).get("file_path", "")
        if not telegram_path:
            return f"[Attached {description}, but download failed]"

        data = await telegram.download_file(telegram_path)

        # Preserve original extension from Telegram path if filename lacks one
        if "." in telegram_path and not Path(file_name).suffix:
            extension = telegram_path.rsplit(".", 1)[-1]
            file_name = f"{file_name}.{extension}"

        local_path = TEMP_DIR / file_name
        local_path.write_bytes(data)
        log.info(
            "Downloaded %s → %s (%d bytes)", description, local_path, len(data),
        )
        return f"[Attached {description}, saved to {local_path}]"

    except Exception as exc:
        log.error("File download failed for %s: %s", description, exc)
        return f"[Attached {description}, download error: {exc}]"
