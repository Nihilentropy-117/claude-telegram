"""Typed domain models shared across subsystems."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import StrEnum
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(tz=UTC)


class ClaudeModel(StrEnum):
    OPUS = "opus"
    SONNET = "sonnet"
    HAIKU = "haiku"


class ClaudeEffort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ThinkingMode(StrEnum):
    OFF = "off"
    ON = "on"


class PromptStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AttachmentKind(StrEnum):
    DOCUMENT = "document"
    PHOTO = "photo"
    VOICE = "voice"
    AUDIO = "audio"
    VIDEO = "video"


class ArtifactType(StrEnum):
    DOCUMENT = "document"
    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"


@dataclass(slots=True)
class UserPreferences:
    user_id: int
    project: str
    model: ClaudeModel
    effort: ClaudeEffort
    think_mode: ThinkingMode = ThinkingMode.OFF
    last_thinking: str = ""
    pending_notice: str | None = None


@dataclass(slots=True)
class UserSessionRecord:
    user_id: int
    resume_supported: bool = False
    resume_token: str | None = None
    started_at: datetime | None = None
    last_reset_reason: str | None = None


@dataclass(slots=True)
class InboundAttachment:
    kind: AttachmentKind
    file_id: str
    file_name: str
    description: str
    local_path: Path
    mime_type: str | None = None


@dataclass(slots=True)
class InboundMessage:
    chat_id: int
    user_id: int
    source_message_id: int
    text: str = ""
    attachments: tuple[InboundAttachment, ...] = ()
    location_text: str | None = None
    contact_text: str | None = None

    def to_prompt(self) -> str | None:
        parts: list[str] = []
        if self.text:
            parts.append(self.text)
        for attachment in self.attachments:
            parts.append(
                f"[Attached {attachment.description}, saved to {attachment.local_path}]"
            )
        if self.location_text:
            parts.append(self.location_text)
        if self.contact_text:
            parts.append(self.contact_text)
        if not parts:
            return None
        return "\n".join(parts)


@dataclass(slots=True)
class QueuedPrompt:
    prompt_id: int
    user_id: int
    chat_id: int
    prompt_text: str
    status: PromptStatus
    source_message_id: int
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None


@dataclass(slots=True)
class QueueEnqueueResult:
    prompt: QueuedPrompt
    requests_ahead: int
    created: bool


@dataclass(slots=True)
class ToolInvocation:
    name: str
    input_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OutboxSnapshotEntry:
    relative_path: str
    size: int
    modified_ns: int


@dataclass(slots=True)
class OutboundArtifact:
    path: Path
    artifact_type: ArtifactType


@dataclass(slots=True)
class UserStatus:
    preferences: UserPreferences
    connected: bool
    queued_requests: int

