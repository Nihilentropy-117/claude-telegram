"""Tests for command dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from claude_telegram.claude.session import UserSession
from claude_telegram.commands import dispatch_command
from claude_telegram.config import Config


@pytest.fixture
def telegram() -> AsyncMock:
    tg = AsyncMock()
    tg.send_message = AsyncMock(return_value={"ok": True})
    return tg


@pytest.fixture
def sessions() -> dict[int, UserSession]:
    return {}


class TestDispatchCommand:
    async def test_help(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        result = await dispatch_command(
            "/help", "", 1, 1, telegram, config, sessions,
        )
        assert result is True
        telegram.send_message.assert_called_once()

    async def test_start(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        result = await dispatch_command(
            "/start", "", 1, 1, telegram, config, sessions,
        )
        assert result is True

    async def test_unknown_command(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        result = await dispatch_command(
            "/unknown", "", 1, 1, telegram, config, sessions,
        )
        assert result is False
        telegram.send_message.assert_not_called()

    async def test_model_valid(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command("/model", "opus", 1, 1, telegram, config, sessions)
        assert sessions[1].model == "opus"

    async def test_model_invalid_keeps_default(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command("/model", "gpt4", 1, 1, telegram, config, sessions)
        assert sessions[1].model == "sonnet"

    async def test_effort_valid(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command("/effort", "low", 1, 1, telegram, config, sessions)
        assert sessions[1].effort == "low"

    async def test_effort_invalid_keeps_default(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command(
            "/effort", "extreme", 1, 1, telegram, config, sessions,
        )
        assert sessions[1].effort == "high"

    async def test_think_on(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command("/think", "on", 1, 1, telegram, config, sessions)
        assert sessions[1].think_mode == "on"

    async def test_think_off(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        # First set to on, then off
        await dispatch_command("/think", "on", 1, 1, telegram, config, sessions)
        await dispatch_command("/think", "off", 1, 1, telegram, config, sessions)
        assert sessions[1].think_mode == "off"

    async def test_think_last_no_thinking(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command("/think", "last", 1, 1, telegram, config, sessions)
        call_text = telegram.send_message.call_args[0][1]
        assert "No thinking" in call_text

    async def test_think_last_with_thinking(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        sessions[1] = UserSession(
            project="/projects", model="sonnet", effort="high",
            last_thinking="I thought about this carefully.",
        )
        await dispatch_command("/think", "last", 1, 1, telegram, config, sessions)
        call_text = telegram.send_message.call_args[0][1]
        assert "I thought about this carefully." in call_text

    async def test_status(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command("/status", "", 1, 1, telegram, config, sessions)
        call_text = telegram.send_message.call_args[0][1]
        assert "sonnet" in call_text
        assert "high" in call_text
        assert "no" in call_text  # Not connected

    async def test_new_session(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command("/new", "", 1, 1, telegram, config, sessions)
        call_text = telegram.send_message.call_args[0][1]
        assert "New session" in call_text

    async def test_project_no_arg_shows_current(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command("/project", "", 1, 1, telegram, config, sessions)
        call_text = telegram.send_message.call_args[0][1]
        assert "/projects" in call_text

    async def test_project_valid_path(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command("/project", "/tmp", 1, 1, telegram, config, sessions)
        assert sessions[1].project == "/tmp"

    async def test_project_invalid_path(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command(
            "/project", "/nonexistent/path", 1, 1, telegram, config, sessions,
        )
        assert sessions[1].project == "/projects"  # Unchanged

    async def test_interrupt_no_session(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        await dispatch_command("/interrupt", "", 1, 1, telegram, config, sessions)
        call_text = telegram.send_message.call_args[0][1]
        assert "No active session" in call_text

    async def test_creates_session_on_first_command(
        self, telegram: AsyncMock, config: Config, sessions: dict,
    ) -> None:
        assert 1 not in sessions
        await dispatch_command("/status", "", 1, 1, telegram, config, sessions)
        assert 1 in sessions
        assert sessions[1].model == "sonnet"
