"""Shared test fixtures."""

from __future__ import annotations

import pytest

from claude_telegram.config import Config


@pytest.fixture
def config() -> Config:
    return Config(
        telegram_token="test-token-123",
        allowed_user_ids=(111, 222),
        telegram_api_base="https://api.telegram.org",
        default_project="/projects",
        default_model="sonnet",
        default_effort="high",
        max_turns=10,
        stream_interval_ms=150,
    )
