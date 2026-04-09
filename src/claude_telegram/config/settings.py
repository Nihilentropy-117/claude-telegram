"""Application settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from claude_telegram.domain.models import ClaudeEffort, ClaudeModel


class AppSettings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_api_base: str = Field(
        default="http://telegram-bot-api:8081",
        alias="TELEGRAM_API_BASE",
    )
    allowed_user_ids_raw: str = Field(default="", alias="ALLOWED_USER_IDS")
    default_project: str = Field(default="/projects", alias="DEFAULT_PROJECT")
    default_model: ClaudeModel = Field(default=ClaudeModel.SONNET, alias="DEFAULT_MODEL")
    default_effort: ClaudeEffort = Field(
        default=ClaudeEffort.HIGH,
        alias="DEFAULT_EFFORT",
    )
    max_turns: int = Field(default=10, alias="MAX_TURNS")
    stream_interval_ms: int = Field(default=150, alias="STREAM_INTERVAL_MS")
    claude_permission_mode: str = Field(
        default="bypassPermissions",
        alias="CLAUDE_PERMISSION_MODE",
    )
    state_db_path: Path = Field(
        default=Path("/settings/state.sqlite3"),
        alias="STATE_DB_PATH",
    )
    temp_dir: Path = Field(default=Path("/temp"), alias="TEMP_DIR")
    outbox_dir: Path = Field(default=Path("/temp/outbox"), alias="OUTBOX_DIR")
    local_bot_api_storage_path: Path = Field(
        default=Path("/var/lib/telegram-bot-api"),
        alias="LOCAL_BOT_API_STORAGE_PATH",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    poll_timeout_seconds: int = Field(default=30, alias="POLL_TIMEOUT_SECONDS")

    @field_validator("telegram_bot_token")
    @classmethod
    def validate_bot_token(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("TELEGRAM_BOT_TOKEN must not be empty.")
        return value

    @field_validator("max_turns")
    @classmethod
    def validate_max_turns(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MAX_TURNS must be greater than zero.")
        return value

    @field_validator("stream_interval_ms")
    @classmethod
    def validate_stream_interval_ms(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("STREAM_INTERVAL_MS must be greater than zero.")
        return value

    @field_validator("poll_timeout_seconds")
    @classmethod
    def validate_poll_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("POLL_TIMEOUT_SECONDS must be greater than zero.")
        return value

    @property
    def allowed_user_ids(self) -> frozenset[int]:
        if not self.allowed_user_ids_raw.strip():
            return frozenset()
        user_ids = {
            int(item.strip())
            for item in self.allowed_user_ids_raw.split(",")
            if item.strip()
        }
        return frozenset(user_ids)

