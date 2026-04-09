"""SQLite connection management."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id INTEGER PRIMARY KEY,
    project TEXT NOT NULL,
    model TEXT NOT NULL,
    effort TEXT NOT NULL,
    think_mode TEXT NOT NULL,
    last_thinking TEXT NOT NULL DEFAULT '',
    pending_notice TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
    user_id INTEGER PRIMARY KEY,
    resume_supported INTEGER NOT NULL DEFAULT 0,
    resume_token TEXT,
    started_at TEXT,
    last_reset_reason TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS queued_prompts (
    prompt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,
    status TEXT NOT NULL,
    source_message_id INTEGER NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, source_message_id)
);

CREATE INDEX IF NOT EXISTS idx_queued_prompts_user_status
    ON queued_prompts(user_id, status, prompt_id);

CREATE TABLE IF NOT EXISTS processed_updates (
    update_id INTEGER PRIMARY KEY,
    processed_at TEXT NOT NULL
);
"""


class Database:
    """Thin wrapper around aiosqlite with serialized setup."""

    def __init__(self, path: Path):
        self._path = path
        self._connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self._path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database connection has not been initialized.")
        return self._connection

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

