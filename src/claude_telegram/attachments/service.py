"""Inbound and outbound file handling."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from urllib import request

from aiogram import Bot
from aiogram.types import Message

from claude_telegram.config.settings import AppSettings
from claude_telegram.domain.models import (
    ArtifactType,
    AttachmentKind,
    InboundAttachment,
    InboundMessage,
    OutboundArtifact,
    OutboxSnapshotEntry,
)

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".aac"}


class AttachmentService:
    """Download inbound attachments and send outbound artifacts."""

    def __init__(self, settings: AppSettings):
        self._settings = settings

    async def extract_message(self, bot: Bot, message: Message) -> InboundMessage | None:
        if message.from_user is None or message.chat is None or message.message_id is None:
            return None

        text = message.caption or message.text or ""
        attachments: list[InboundAttachment] = []
        location_text: str | None = None
        contact_text: str | None = None

        attachment = await self._extract_attachment(bot, message)
        if attachment is not None:
            attachments.append(attachment)

        if message.location is not None:
            location_text = (
                f"[User shared a location: {message.location.latitude}, "
                f"{message.location.longitude}]"
            )

        if message.contact is not None:
            first_name = message.contact.first_name or ""
            last_name = message.contact.last_name or ""
            name = f"{first_name} {last_name}".strip()
            contact_text = (
                f"[User shared a contact: {name or 'unknown'}, "
                f"phone: {message.contact.phone_number}]"
            )

        inbound = InboundMessage(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            source_message_id=message.message_id,
            text=text,
            attachments=tuple(attachments),
            location_text=location_text,
            contact_text=contact_text,
        )
        if inbound.to_prompt() is None:
            return None
        return inbound

    async def snapshot_outbox(self) -> dict[str, OutboxSnapshotEntry]:
        snapshot: dict[str, OutboxSnapshotEntry] = {}
        if not self._settings.outbox_dir.exists():
            return snapshot
        for path in sorted(self._settings.outbox_dir.rglob("*")):
            if not path.is_file():
                continue
            stat_result = path.stat()
            relative_path = str(path.relative_to(self._settings.outbox_dir))
            snapshot[relative_path] = OutboxSnapshotEntry(
                relative_path=relative_path,
                size=stat_result.st_size,
                modified_ns=stat_result.st_mtime_ns,
            )
        return snapshot

    async def collect_new_artifacts(
        self,
        before_snapshot: dict[str, OutboxSnapshotEntry],
    ) -> list[OutboundArtifact]:
        artifacts: list[OutboundArtifact] = []
        if not self._settings.outbox_dir.exists():
            return artifacts
        # NOTE: The outbox is shared across runs, so snapshot diffs are used to
        # avoid resending older artifacts while preserving the legacy directory contract.
        for path in sorted(self._settings.outbox_dir.rglob("*")):
            if not path.is_file():
                continue
            stat_result = path.stat()
            relative_path = str(path.relative_to(self._settings.outbox_dir))
            previous = before_snapshot.get(relative_path)
            if previous is not None and previous.size == stat_result.st_size and previous.modified_ns == stat_result.st_mtime_ns:
                continue
            artifact_type = self._artifact_type(path)
            artifacts.append(OutboundArtifact(path=path, artifact_type=artifact_type))
        return artifacts

    async def send_artifacts(self, bot: Bot, chat_id: int, artifacts: list[OutboundArtifact]) -> None:
        for artifact in artifacts:
            if artifact.artifact_type is ArtifactType.PHOTO:
                await bot.send_photo(chat_id=chat_id, photo=artifact.path)
            elif artifact.artifact_type is ArtifactType.VIDEO:
                await bot.send_video(chat_id=chat_id, video=artifact.path)
            elif artifact.artifact_type is ArtifactType.AUDIO:
                await bot.send_audio(chat_id=chat_id, audio=artifact.path)
            else:
                await bot.send_document(chat_id=chat_id, document=artifact.path)
            artifact.path.unlink(missing_ok=True)

    async def _extract_attachment(self, bot: Bot, message: Message) -> InboundAttachment | None:
        file_id: str | None = None
        file_name: str | None = None
        description: str | None = None
        mime_type: str | None = None
        kind: AttachmentKind | None = None

        if message.document is not None:
            file_id = message.document.file_id
            file_name = message.document.file_name or f"document_{file_id[:8]}"
            description = f"document ({message.document.mime_type or 'unknown type'})"
            mime_type = message.document.mime_type
            kind = AttachmentKind.DOCUMENT
        elif message.photo:
            largest_photo = message.photo[-1]
            file_id = largest_photo.file_id
            file_name = f"photo_{file_id[:8]}.jpg"
            description = f"photo ({largest_photo.width}x{largest_photo.height})"
            kind = AttachmentKind.PHOTO
        elif message.voice is not None:
            file_id = message.voice.file_id
            file_name = f"voice_{file_id[:8]}.ogg"
            description = f"voice message ({message.voice.duration}s)"
            mime_type = message.voice.mime_type
            kind = AttachmentKind.VOICE
        elif message.audio is not None:
            file_id = message.audio.file_id
            file_name = message.audio.file_name or f"audio_{file_id[:8]}.mp3"
            performer = message.audio.performer or ""
            title = message.audio.title or ""
            label = f"{performer} - {title}".strip(" -") or file_name
            description = f"audio file: {label} ({message.audio.duration}s)"
            mime_type = message.audio.mime_type
            kind = AttachmentKind.AUDIO
        elif message.video is not None:
            file_id = message.video.file_id
            file_name = message.video.file_name or f"video_{file_id[:8]}.mp4"
            description = (
                f"video ({message.video.width}x{message.video.height}, "
                f"{message.video.duration}s)"
            )
            mime_type = message.video.mime_type
            kind = AttachmentKind.VIDEO

        if file_id is None or file_name is None or description is None or kind is None:
            return None

        telegram_file = await bot.get_file(file_id)
        file_path = telegram_file.file_path
        if file_path is None:
            raise RuntimeError(f"Telegram returned no file path for {file_id}.")
        local_path = await self._save_file(bot, file_path, file_name)
        return InboundAttachment(
            kind=kind,
            file_id=file_id,
            file_name=file_name,
            description=description,
            local_path=local_path,
            mime_type=mime_type,
        )

    async def _save_file(self, bot: Bot, file_path: str, file_name: str) -> Path:
        self._settings.temp_dir.mkdir(parents=True, exist_ok=True)
        destination = self._settings.temp_dir / file_name
        if file_path.startswith("/"):
            source_path = Path(file_path)
        else:
            source_path = self._settings.local_bot_api_storage_path / file_path
        if source_path.exists():
            destination.write_bytes(source_path.read_bytes())
            return destination
        await asyncio.to_thread(self._download_via_bot_api, bot.token, file_path, destination)
        return destination

    def _download_via_bot_api(self, token: str, file_path: str, destination: Path) -> None:
        file_url = f"{self._settings.telegram_api_base.rstrip('/')}/file/bot{token}/{file_path}"
        with request.urlopen(file_url, timeout=120) as response:
            destination.write_bytes(response.read())

    def _artifact_type(self, path: Path) -> ArtifactType:
        extension = path.suffix.lower()
        if extension in IMAGE_EXTENSIONS:
            return ArtifactType.PHOTO
        if extension in VIDEO_EXTENSIONS:
            return ArtifactType.VIDEO
        if extension in AUDIO_EXTENSIONS:
            return ArtifactType.AUDIO
        return ArtifactType.DOCUMENT
