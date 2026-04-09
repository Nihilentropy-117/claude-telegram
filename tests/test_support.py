"""Shared test helpers."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from claude_telegram.config.settings import AppSettings


@contextmanager
def configured_settings() -> AppSettings:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        env = {
            "TELEGRAM_BOT_TOKEN": "123456:TESTTOKEN",
            "ALLOWED_USER_IDS": "1,2",
            "DEFAULT_PROJECT": "/projects",
            "DEFAULT_MODEL": "sonnet",
            "DEFAULT_EFFORT": "high",
            "MAX_TURNS": "10",
            "STREAM_INTERVAL_MS": "150",
            "CLAUDE_PERMISSION_MODE": "bypassPermissions",
            "STATE_DB_PATH": str(root / "state.sqlite3"),
            "TEMP_DIR": str(root / "temp"),
            "OUTBOX_DIR": str(root / "temp" / "outbox"),
            "LOCAL_BOT_API_STORAGE_PATH": str(root / "telegram-files"),
            "POLL_TIMEOUT_SECONDS": "30",
            "LOG_LEVEL": "INFO",
            "TELEGRAM_API_BASE": "http://localhost:8081",
        }
        with patch.dict(os.environ, env, clear=True):
            yield AppSettings()
