"""Per-user Claude SDK session management."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

if TYPE_CHECKING:
    from claude_telegram.config import Config

log = logging.getLogger(__name__)

MODEL_IDS: dict[str, str] = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}


@dataclass
class UserSession:
    """Mutable per-user state: configuration preferences and SDK client."""

    project: str
    model: str
    effort: str
    think_mode: str = "off"  # "off" | "on" | "last"
    last_thinking: str = ""
    busy: bool = False
    _client: ClaudeSDKClient | None = field(default=None, repr=False)

    def _build_options(self, config: Config) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            cwd=self.project,
            max_turns=config.max_turns,
            effort=self.effort,
            system_prompt=(
                "You are Claude Code, accessed via Telegram. "
                "Keep responses concise for mobile reading. "
                "Use markdown formatting compatible with Telegram. "
                "You have full root access in a sandboxed Docker container. "
                "Install any packages you need freely — pip uses a persistent "
                "venv at /venv, apt cache is persistent. "
                "To send a file to the user, write it to /temp/outbox/ — "
                "the bot will automatically deliver it to Telegram after your "
                "response. See ~/.claude/CLAUDE.md for full details."
            ),
            setting_sources=["user", "project", "local"],
            env={
                "HOME": "/root",
                "ANTHROPIC_MODEL": MODEL_IDS[self.model],
                "IS_SANDBOX": "1",
            },
        )

    async def get_client(self, config: Config) -> ClaudeSDKClient:
        if self._client is None:
            options = self._build_options(config)
            self._client = ClaudeSDKClient(options=options)
            await self._client.connect()
            log.info(
                "SDK client connected (cwd=%s, model=%s)",
                self.project,
                self.model,
            )
        return self._client

    async def interrupt(self) -> None:
        if self._client is None:
            raise RuntimeError("No active session")
        await self._client.interrupt()

    async def destroy_client(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                log.debug("Error disconnecting SDK client", exc_info=True)
            self._client = None

    async def reset(self) -> None:
        """Destroy the current session so the next query starts fresh."""
        await self.destroy_client()

    @property
    def connected(self) -> bool:
        return self._client is not None


def get_or_create_session(
    user_id: int, sessions: dict[int, UserSession], config: Config,
) -> UserSession:
    """Return the existing session for a user, or create one with defaults."""
    return sessions.setdefault(
        user_id,
        UserSession(
            project=config.default_project,
            model=config.default_model,
            effort=config.default_effort,
        ),
    )
