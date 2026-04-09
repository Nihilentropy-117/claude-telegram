"""Application configuration loaded from environment variables."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass

log = logging.getLogger(__name__)

VALID_MODELS = frozenset({"opus", "sonnet", "haiku"})
VALID_EFFORTS = frozenset({"low", "medium", "high"})


@dataclass(frozen=True)
class Config:
    """Immutable application configuration. All values sourced from environment."""

    telegram_token: str
    allowed_user_ids: tuple[int, ...]
    telegram_api_base: str
    default_project: str
    default_model: str
    default_effort: str
    max_turns: int
    stream_interval_ms: int

    @classmethod
    def from_env(cls) -> Config:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            log.error("TELEGRAM_BOT_TOKEN is required")
            sys.exit(1)

        raw_ids = os.environ.get("ALLOWED_USER_IDS", "")
        allowed_ids = tuple(int(x.strip()) for x in raw_ids.split(",") if x.strip())
        if not allowed_ids:
            log.warning("ALLOWED_USER_IDS not set — bot is open to everyone!")

        model = os.environ.get("DEFAULT_MODEL", "sonnet").lower()
        if model not in VALID_MODELS:
            log.error("DEFAULT_MODEL must be one of %s, got '%s'", VALID_MODELS, model)
            sys.exit(1)

        effort = os.environ.get("DEFAULT_EFFORT", "high").lower()
        if effort not in VALID_EFFORTS:
            log.error("DEFAULT_EFFORT must be one of %s, got '%s'", VALID_EFFORTS, effort)
            sys.exit(1)

        return cls(
            telegram_token=token,
            allowed_user_ids=allowed_ids,
            telegram_api_base=os.environ.get(
                "TELEGRAM_API_BASE", "https://api.telegram.org"
            ),
            default_project=os.environ.get("DEFAULT_PROJECT", "/projects"),
            default_model=model,
            default_effort=effort,
            max_turns=int(os.environ.get("MAX_TURNS", "10")),
            stream_interval_ms=int(os.environ.get("STREAM_INTERVAL_MS", "150")),
        )
