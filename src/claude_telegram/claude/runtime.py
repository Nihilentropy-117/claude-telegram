"""Claude SDK session management."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass

from claude_telegram.claude.events import ClaudeRunEvent, RunFinished, TextDelta, ThinkingDelta, ToolStarted
from claude_telegram.config.settings import AppSettings
from claude_telegram.domain.models import ClaudeModel, ToolInvocation, UserPreferences, UserSessionRecord, utc_now
from claude_telegram.persistence.repositories import SessionRepository

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Claude Code, accessed via Telegram. "
    "Keep responses concise for mobile reading. "
    "The Telegram bridge sends assistant output as plain text for deterministic rendering. "
    "You have full root access in a sandboxed Docker container. "
    "The Python environment at /venv is persistent across container restarts. "
    "To send a file to the user, write it to /temp/outbox/ and the bridge will deliver it after your response. "
    "See ~/.claude/CLAUDE.md for environment details."
)

MODEL_ENV_MAP = {
    ClaudeModel.OPUS: "claude-opus-4-6",
    ClaudeModel.SONNET: "claude-sonnet-4-6",
    ClaudeModel.HAIKU: "claude-haiku-4-5",
}


class ClaudeRuntimeError(RuntimeError):
    """Raised for Claude runtime failures."""


def translate_assistant_blocks(blocks: Iterable[object]) -> list[ClaudeRunEvent]:
    """Translate Claude SDK content blocks into internal events."""
    events: list[ClaudeRunEvent] = []
    for block in blocks:
        if hasattr(block, "text"):
            text = getattr(block, "text")
            if isinstance(text, str):
                events.append(TextDelta(text=text))
                continue
        if hasattr(block, "thinking"):
            thinking = getattr(block, "thinking")
            if isinstance(thinking, str):
                events.append(ThinkingDelta(text=thinking))
                continue
        if hasattr(block, "name"):
            name = getattr(block, "name")
            if isinstance(name, str):
                input_payload = getattr(block, "input", {}) or {}
                if not isinstance(input_payload, dict):
                    input_payload = {}
                events.append(
                    ToolStarted(invocation=ToolInvocation(name=name, input_payload=input_payload))
                )
    return events


@dataclass(slots=True)
class ClaudeSession:
    """Persistent Claude SDK client for one Telegram user."""

    user_id: int
    preferences: UserPreferences
    settings: AppSettings
    _client: object | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        try:
            from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
        except ImportError as exc:
            raise ClaudeRuntimeError("claude-agent-sdk is not installed.") from exc

        options = ClaudeAgentOptions(
            permission_mode=self.settings.claude_permission_mode,
            cwd=self.preferences.project,
            max_turns=self.settings.max_turns,
            effort=self.preferences.effort.value,
            system_prompt=SYSTEM_PROMPT,
            env={
                "ANTHROPIC_MODEL": MODEL_ENV_MAP[self.preferences.model],
                "IS_SANDBOX": "1",
            },
        )
        client = ClaudeSDKClient(options=options)
        await client.connect()
        self._client = client

    async def iter_events(self, prompt: str) -> AsyncIterator[ClaudeRunEvent]:
        await self.connect()
        if self._client is None:
            raise ClaudeRuntimeError("Claude client is not connected.")

        try:
            await self._client.query(prompt)
            async for message in self._client.receive_response():
                class_name = type(message).__name__
                if class_name == "AssistantMessage":
                    for event in translate_assistant_blocks(getattr(message, "content", ())):
                        yield event
                elif class_name == "ResultMessage":
                    total_cost = getattr(message, "total_cost_usd", None)
                    yield RunFinished(total_cost_usd=total_cost)
        except Exception as exc:
            raise ClaudeRuntimeError(str(exc)) from exc

    async def interrupt(self) -> bool:
        if self._client is None:
            return False
        try:
            await self._client.interrupt()
        except Exception as exc:
            raise ClaudeRuntimeError("Failed to interrupt Claude session.") from exc
        return True

    async def close(self) -> None:
        if self._client is None:
            return
        client = self._client
        self._client = None
        try:
            await client.disconnect()
        except Exception as exc:
            raise ClaudeRuntimeError("Failed to disconnect Claude session cleanly.") from exc


class ClaudeSessionPool:
    """Cache and lifecycle management for per-user Claude sessions."""

    def __init__(self, settings: AppSettings, session_repository: SessionRepository):
        self._settings = settings
        self._session_repository = session_repository
        self._sessions: dict[int, ClaudeSession] = {}

    async def get_or_create(
        self,
        preferences: UserPreferences,
        record: UserSessionRecord,
    ) -> ClaudeSession:
        session = self._sessions.get(preferences.user_id)
        if session is not None and session.preferences == preferences:
            return session
        if session is not None:
            await self.reset(preferences.user_id, reason="session configuration changed")
        session = ClaudeSession(
            user_id=preferences.user_id,
            preferences=preferences,
            settings=self._settings,
        )
        self._sessions[preferences.user_id] = session
        # NOTE: Claude SDK currently documents session forking but not a stable
        # cross-process resume token, so metadata is persisted separately and
        # sessions are recreated after restart.
        await self._session_repository.upsert(
            UserSessionRecord(
                user_id=preferences.user_id,
                resume_supported=record.resume_supported,
                resume_token=record.resume_token,
                started_at=utc_now(),
                last_reset_reason=None,
            )
        )
        return session

    async def reset(self, user_id: int, reason: str) -> None:
        session = self._sessions.pop(user_id, None)
        if session is not None:
            try:
                await session.close()
            except ClaudeRuntimeError:
                log.warning("Claude session close failed during reset for user %s.", user_id, exc_info=True)
        await self._session_repository.upsert(
            UserSessionRecord(
                user_id=user_id,
                resume_supported=False,
                resume_token=None,
                started_at=None,
                last_reset_reason=reason,
            )
        )

    async def interrupt(self, user_id: int) -> bool:
        session = self._sessions.get(user_id)
        if session is None:
            return False
        return await session.interrupt()

    def has_active_session(self, user_id: int) -> bool:
        return user_id in self._sessions

    async def shutdown(self) -> None:
        for user_id in list(self._sessions):
            await self.reset(user_id, reason="application shutdown")

