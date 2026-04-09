"""SQLite-backed repositories."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from claude_telegram.config.settings import AppSettings
from claude_telegram.domain.models import (
    ClaudeEffort,
    ClaudeModel,
    PromptStatus,
    QueueEnqueueResult,
    QueuedPrompt,
    ThinkingMode,
    UserPreferences,
    UserSessionRecord,
    utc_now,
)
from claude_telegram.persistence.database import Database


def _timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def _nullable_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


class PreferencesRepository:
    """Persisted per-user preferences."""

    def __init__(self, database: Database, settings: AppSettings):
        self._database = database
        self._settings = settings

    async def get_or_create(self, user_id: int) -> UserPreferences:
        preferences = UserPreferences(
            user_id=user_id,
            project=self._settings.default_project,
            model=self._settings.default_model,
            effort=self._settings.default_effort,
        )
        async with self._database.lock:
            cursor = await self._database.connection.execute(
                """
                SELECT user_id, project, model, effort, think_mode, last_thinking, pending_notice
                FROM user_preferences
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                await self._database.connection.execute(
                    """
                    INSERT INTO user_preferences (
                        user_id, project, model, effort, think_mode, last_thinking, pending_notice, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        preferences.user_id,
                        preferences.project,
                        preferences.model.value,
                        preferences.effort.value,
                        preferences.think_mode.value,
                        preferences.last_thinking,
                        preferences.pending_notice,
                        _timestamp(),
                    ),
                )
                await self._database.connection.commit()
                return preferences
            return UserPreferences(
                user_id=row["user_id"],
                project=row["project"],
                model=ClaudeModel(row["model"]),
                effort=ClaudeEffort(row["effort"]),
                think_mode=ThinkingMode(row["think_mode"]),
                last_thinking=row["last_thinking"],
                pending_notice=row["pending_notice"],
            )

    async def upsert(self, preferences: UserPreferences) -> None:
        async with self._database.lock:
            await self._database.connection.execute(
                """
                INSERT INTO user_preferences (
                    user_id, project, model, effort, think_mode, last_thinking, pending_notice, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    project = excluded.project,
                    model = excluded.model,
                    effort = excluded.effort,
                    think_mode = excluded.think_mode,
                    last_thinking = excluded.last_thinking,
                    pending_notice = excluded.pending_notice,
                    updated_at = excluded.updated_at
                """,
                (
                    preferences.user_id,
                    preferences.project,
                    preferences.model.value,
                    preferences.effort.value,
                    preferences.think_mode.value,
                    preferences.last_thinking,
                    preferences.pending_notice,
                    _timestamp(),
                ),
            )
            await self._database.connection.commit()


class SessionRepository:
    """Persisted Claude session metadata."""

    def __init__(self, database: Database):
        self._database = database

    async def get(self, user_id: int) -> UserSessionRecord:
        async with self._database.lock:
            cursor = await self._database.connection.execute(
                """
                SELECT user_id, resume_supported, resume_token, started_at, last_reset_reason
                FROM user_sessions
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                return UserSessionRecord(user_id=user_id)
            return UserSessionRecord(
                user_id=row["user_id"],
                resume_supported=bool(row["resume_supported"]),
                resume_token=row["resume_token"],
                started_at=_parse_timestamp(row["started_at"]),
                last_reset_reason=row["last_reset_reason"],
            )

    async def upsert(self, record: UserSessionRecord) -> None:
        async with self._database.lock:
            await self._database.connection.execute(
                """
                INSERT INTO user_sessions (
                    user_id, resume_supported, resume_token, started_at, last_reset_reason, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    resume_supported = excluded.resume_supported,
                    resume_token = excluded.resume_token,
                    started_at = excluded.started_at,
                    last_reset_reason = excluded.last_reset_reason,
                    updated_at = excluded.updated_at
                """,
                (
                    record.user_id,
                    int(record.resume_supported),
                    record.resume_token,
                    _nullable_timestamp(record.started_at),
                    record.last_reset_reason,
                    _timestamp(),
                ),
            )
            await self._database.connection.commit()


class QueueRepository:
    """Persisted user prompt queue."""

    def __init__(self, database: Database):
        self._database = database

    async def enqueue(
        self,
        user_id: int,
        chat_id: int,
        prompt_text: str,
        source_message_id: int,
    ) -> QueueEnqueueResult:
        async with self._database.lock:
            created_at = _timestamp()
            try:
                cursor = await self._database.connection.execute(
                    """
                    INSERT INTO queued_prompts (
                        user_id, chat_id, prompt_text, status, source_message_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        chat_id,
                        prompt_text,
                        PromptStatus.QUEUED.value,
                        source_message_id,
                        created_at,
                        created_at,
                    ),
                )
                prompt_id = cursor.lastrowid
                created = True
            except sqlite3.IntegrityError:
                cursor = await self._database.connection.execute(
                    """
                    SELECT prompt_id
                    FROM queued_prompts
                    WHERE user_id = ? AND source_message_id = ?
                    """,
                    (user_id, source_message_id),
                )
                existing = await cursor.fetchone()
                if existing is None:
                    raise
                prompt_id = existing["prompt_id"]
                created = False
            count_cursor = await self._database.connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM queued_prompts
                WHERE user_id = ?
                  AND status IN (?, ?)
                  AND prompt_id < ?
                """,
                (
                    user_id,
                    PromptStatus.QUEUED.value,
                    PromptStatus.RUNNING.value,
                    prompt_id,
                ),
            )
            count_row = await count_cursor.fetchone()
            await count_cursor.close()
            await self._database.connection.commit()
        prompt = await self.get_by_id(prompt_id)
        return QueueEnqueueResult(
            prompt=prompt,
            requests_ahead=count_row["total"] if count_row else 0,
            created=created,
        )

    async def get_by_id(self, prompt_id: int) -> QueuedPrompt:
        async with self._database.lock:
            cursor = await self._database.connection.execute(
                """
                SELECT prompt_id, user_id, chat_id, prompt_text, status, source_message_id,
                       created_at, updated_at, error_message
                FROM queued_prompts
                WHERE prompt_id = ?
                """,
                (prompt_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                raise LookupError(f"Queued prompt {prompt_id} does not exist.")
            return QueuedPrompt(
                prompt_id=row["prompt_id"],
                user_id=row["user_id"],
                chat_id=row["chat_id"],
                prompt_text=row["prompt_text"],
                status=PromptStatus(row["status"]),
                source_message_id=row["source_message_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                error_message=row["error_message"],
            )

    async def next_queued(self, user_id: int) -> QueuedPrompt | None:
        async with self._database.lock:
            cursor = await self._database.connection.execute(
                """
                SELECT prompt_id
                FROM queued_prompts
                WHERE user_id = ? AND status = ?
                ORDER BY prompt_id ASC
                LIMIT 1
                """,
                (user_id, PromptStatus.QUEUED.value),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            return None
        return await self.get_by_id(row["prompt_id"])

    async def mark_running(self, prompt_id: int) -> None:
        await self._update_status(prompt_id, PromptStatus.RUNNING)

    async def mark_completed(self, prompt_id: int) -> None:
        await self._update_status(prompt_id, PromptStatus.COMPLETED)

    async def mark_failed(self, prompt_id: int, error_message: str) -> None:
        async with self._database.lock:
            await self._database.connection.execute(
                """
                UPDATE queued_prompts
                SET status = ?, error_message = ?, updated_at = ?
                WHERE prompt_id = ?
                """,
                (
                    PromptStatus.FAILED.value,
                    error_message,
                    _timestamp(),
                    prompt_id,
                ),
            )
            await self._database.connection.commit()

    async def mark_stale_running_jobs_failed(self, error_message: str) -> list[int]:
        async with self._database.lock:
            cursor = await self._database.connection.execute(
                """
                SELECT DISTINCT user_id
                FROM queued_prompts
                WHERE status = ?
                """,
                (PromptStatus.RUNNING.value,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            user_ids = [row["user_id"] for row in rows]
            await self._database.connection.execute(
                """
                UPDATE queued_prompts
                SET status = ?, error_message = ?, updated_at = ?
                WHERE status = ?
                """,
                (
                    PromptStatus.FAILED.value,
                    error_message,
                    _timestamp(),
                    PromptStatus.RUNNING.value,
                ),
            )
            await self._database.connection.commit()
            return user_ids

    async def list_users_with_queued_prompts(self) -> list[int]:
        async with self._database.lock:
            cursor = await self._database.connection.execute(
                """
                SELECT DISTINCT user_id
                FROM queued_prompts
                WHERE status = ?
                ORDER BY user_id ASC
                """,
                (PromptStatus.QUEUED.value,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [row["user_id"] for row in rows]

    async def count_open_prompts(self, user_id: int) -> int:
        async with self._database.lock:
            cursor = await self._database.connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM queued_prompts
                WHERE user_id = ? AND status IN (?, ?)
                """,
                (
                    user_id,
                    PromptStatus.QUEUED.value,
                    PromptStatus.RUNNING.value,
                ),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return int(row["total"]) if row is not None else 0

    async def _update_status(self, prompt_id: int, status: PromptStatus) -> None:
        async with self._database.lock:
            await self._database.connection.execute(
                """
                UPDATE queued_prompts
                SET status = ?, updated_at = ?
                WHERE prompt_id = ?
                """,
                (status.value, _timestamp(), prompt_id),
            )
            await self._database.connection.commit()


class UpdateRepository:
    """Track processed Telegram update offsets."""

    def __init__(self, database: Database):
        self._database = database

    async def is_processed(self, update_id: int) -> bool:
        async with self._database.lock:
            cursor = await self._database.connection.execute(
                "SELECT 1 FROM processed_updates WHERE update_id = ?",
                (update_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return row is not None

    async def mark_processed(self, update_id: int) -> None:
        async with self._database.lock:
            await self._database.connection.execute(
                """
                INSERT OR IGNORE INTO processed_updates (update_id, processed_at)
                VALUES (?, ?)
                """,
                (update_id, _timestamp()),
            )
            await self._database.connection.commit()

    async def next_offset(self) -> int | None:
        async with self._database.lock:
            cursor = await self._database.connection.execute(
                "SELECT MAX(update_id) AS max_update_id FROM processed_updates"
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None or row["max_update_id"] is None:
                return None
            return int(row["max_update_id"]) + 1
