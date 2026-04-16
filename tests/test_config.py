"""Tests for configuration loading."""

from __future__ import annotations

import pytest

from claude_telegram.config import Config


class TestConfigFromEnv:
    def test_minimal_valid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("ALLOWED_USER_IDS", "123,456")
        config = Config.from_env()
        assert config.telegram_token == "test-token"
        assert config.allowed_user_ids == (123, 456)
        assert config.default_model == "sonnet"
        assert config.default_effort == "high"
        assert config.max_turns == 10
        assert config.stream_interval_ms == 150

    def test_missing_token_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with pytest.raises(SystemExit):
            Config.from_env()

    def test_empty_allowed_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("ALLOWED_USER_IDS", "")
        config = Config.from_env()
        assert config.allowed_user_ids == ()

    def test_custom_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("ALLOWED_USER_IDS", "1")
        monkeypatch.setenv("DEFAULT_MODEL", "opus")
        monkeypatch.setenv("DEFAULT_EFFORT", "low")
        monkeypatch.setenv("MAX_TURNS", "20")
        monkeypatch.setenv("STREAM_INTERVAL_MS", "200")
        monkeypatch.setenv("DEFAULT_PROJECT", "/custom")
        monkeypatch.setenv("TELEGRAM_API_BASE", "http://localhost:8081")
        config = Config.from_env()
        assert config.default_model == "opus"
        assert config.default_effort == "low"
        assert config.max_turns == 20
        assert config.stream_interval_ms == 200
        assert config.default_project == "/custom"
        assert config.telegram_api_base == "http://localhost:8081"

    def test_invalid_model_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("ALLOWED_USER_IDS", "1")
        monkeypatch.setenv("DEFAULT_MODEL", "gpt4")
        with pytest.raises(SystemExit):
            Config.from_env()

    def test_invalid_effort_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("ALLOWED_USER_IDS", "1")
        monkeypatch.setenv("DEFAULT_EFFORT", "extreme")
        with pytest.raises(SystemExit):
            Config.from_env()

    def test_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("ALLOWED_USER_IDS", "1")
        config = Config.from_env()
        with pytest.raises(AttributeError):
            config.telegram_token = "changed"  # type: ignore[misc]
