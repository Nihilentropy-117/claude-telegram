"""Per-user queue and run orchestration."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from claude_telegram.attachments.service import AttachmentService
from claude_telegram.claude.events import RunFinished, TextDelta, ThinkingDelta, ToolStarted
from claude_telegram.claude.runtime import ClaudeRuntimeError, ClaudeSessionPool
from claude_telegram.domain.models import (
    ClaudeEffort,
    ClaudeModel,
    InboundMessage,
    QueueEnqueueResult,
    ThinkingMode,
    UserPreferences,
    UserStatus,
)
from claude_telegram.persistence.repositories import PreferencesRepository, QueueRepository, SessionRepository
from claude_telegram.telegram.presenter import TelegramPresenter

log = logging.getLogger(__name__)


class SessionCoordinator:
    """Coordinate persisted queues, Claude sessions, and Telegram output."""

    def __init__(
        self,
        bot: Bot,
        presenter: TelegramPresenter,
        attachment_service: AttachmentService,
        preferences_repository: PreferencesRepository,
        session_repository: SessionRepository,
        queue_repository: QueueRepository,
        claude_pool: ClaudeSessionPool,
    ):
        self._bot = bot
        self._presenter = presenter
        self._attachment_service = attachment_service
        self._preferences_repository = preferences_repository
        self._session_repository = session_repository
        self._queue_repository = queue_repository
        self._claude_pool = claude_pool
        self._worker_tasks: dict[int, asyncio.Task[None]] = {}
        self._worker_locks: dict[int, asyncio.Lock] = {}
        self._interrupted_users: set[int] = set()

    async def recover(self) -> None:
        stale_user_ids = await self._queue_repository.mark_stale_running_jobs_failed(
            "The bot restarted while this request was running."
        )
        for user_id in stale_user_ids:
            preferences = await self._preferences_repository.get_or_create(user_id)
            preferences.pending_notice = (
                "The previous in-progress request failed because the bot restarted."
            )
            await self._preferences_repository.upsert(preferences)
        for user_id in await self._queue_repository.list_users_with_queued_prompts():
            self._ensure_worker(user_id)

    async def shutdown(self) -> None:
        for task in self._worker_tasks.values():
            task.cancel()
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks.values(), return_exceptions=True)
        await self._claude_pool.shutdown()

    async def enqueue_message(self, message: InboundMessage) -> QueueEnqueueResult:
        prompt = message.to_prompt()
        if prompt is None:
            raise ValueError("Cannot enqueue an empty prompt.")
        result = await self._queue_repository.enqueue(
            user_id=message.user_id,
            chat_id=message.chat_id,
            prompt_text=prompt,
            source_message_id=message.source_message_id,
        )
        self._ensure_worker(message.user_id)
        return result

    async def reset_session(self, user_id: int, reason: str, interrupt_running: bool = True) -> None:
        if interrupt_running:
            await self.interrupt(user_id)
        await self._claude_pool.reset(user_id, reason=reason)

    async def interrupt(self, user_id: int) -> bool:
        interrupted = await self._claude_pool.interrupt(user_id)
        if interrupted:
            self._interrupted_users.add(user_id)
        return interrupted

    async def update_project(self, user_id: int, project: str) -> UserPreferences:
        preferences = await self._preferences_repository.get_or_create(user_id)
        preferences.project = project
        await self._preferences_repository.upsert(preferences)
        await self.reset_session(user_id, reason="project changed")
        return preferences

    async def update_model(self, user_id: int, model: ClaudeModel) -> UserPreferences:
        preferences = await self._preferences_repository.get_or_create(user_id)
        preferences.model = model
        await self._preferences_repository.upsert(preferences)
        await self.reset_session(user_id, reason="model changed")
        return preferences

    async def update_effort(self, user_id: int, effort: ClaudeEffort) -> UserPreferences:
        preferences = await self._preferences_repository.get_or_create(user_id)
        preferences.effort = effort
        await self._preferences_repository.upsert(preferences)
        await self.reset_session(user_id, reason="effort changed")
        return preferences

    async def update_thinking_mode(self, user_id: int, think_mode: ThinkingMode) -> UserPreferences:
        preferences = await self._preferences_repository.get_or_create(user_id)
        preferences.think_mode = think_mode
        await self._preferences_repository.upsert(preferences)
        return preferences

    async def get_preferences(self, user_id: int) -> UserPreferences:
        return await self._preferences_repository.get_or_create(user_id)

    async def get_status(self, user_id: int) -> UserStatus:
        preferences = await self._preferences_repository.get_or_create(user_id)
        return UserStatus(
            preferences=preferences,
            connected=self._claude_pool.has_active_session(user_id),
            queued_requests=await self._queue_repository.count_open_prompts(user_id),
        )

    async def _worker(self, user_id: int) -> None:
        lock = self._worker_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            while True:
                prompt = await self._queue_repository.next_queued(user_id)
                if prompt is None:
                    break
                preferences = await self._preferences_repository.get_or_create(user_id)
                if preferences.pending_notice:
                    await self._presenter.send_plain(prompt.chat_id, preferences.pending_notice)
                    preferences.pending_notice = None
                    await self._preferences_repository.upsert(preferences)

                await self._queue_repository.mark_running(prompt.prompt_id)
                bridge = self._presenter.create_stream_bridge(prompt.chat_id)
                before_snapshot = await self._attachment_service.snapshot_outbox()
                assistant_parts: list[str] = []
                thinking_parts: list[str] = []
                try:
                    await self._presenter.send_typing(prompt.chat_id)
                    session_record = await self._session_repository.get(user_id)
                    session = await self._claude_pool.get_or_create(preferences, session_record)
                    async for event in session.iter_events(prompt.prompt_text):
                        if isinstance(event, TextDelta):
                            assistant_parts.append(event.text)
                            await bridge.push_text(event.text)
                        elif isinstance(event, ThinkingDelta):
                            thinking_parts.append(event.text)
                        elif isinstance(event, ToolStarted):
                            await self._presenter.send_tool_status(prompt.chat_id, event.invocation)
                        elif isinstance(event, RunFinished) and event.total_cost_usd is not None:
                            log.info("Claude request for user %s cost $%.4f", user_id, event.total_cost_usd)

                    final_text = "".join(assistant_parts)
                    thinking_text = "\n".join(part for part in thinking_parts if part)
                    preferences.last_thinking = thinking_text
                    await self._preferences_repository.upsert(preferences)
                    if preferences.think_mode is ThinkingMode.ON and thinking_text:
                        await self._presenter.send_thinking(prompt.chat_id, thinking_text)
                    await bridge.finalize(final_text)
                    new_artifacts = await self._attachment_service.collect_new_artifacts(before_snapshot)
                    await self._attachment_service.send_artifacts(self._bot, prompt.chat_id, new_artifacts)
                    await self._queue_repository.mark_completed(prompt.prompt_id)
                    self._interrupted_users.discard(user_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if user_id in self._interrupted_users:
                        self._interrupted_users.discard(user_id)
                        await self._queue_repository.mark_failed(prompt.prompt_id, "Interrupted by user.")
                    else:
                        await self._queue_repository.mark_failed(prompt.prompt_id, str(exc))
                        await self._presenter.send_error(prompt.chat_id, str(exc))
                        await self._claude_pool.reset(user_id, reason="runtime error")
        self._worker_tasks.pop(user_id, None)

    def _ensure_worker(self, user_id: int) -> None:
        task = self._worker_tasks.get(user_id)
        if task is not None and not task.done():
            return
        self._worker_tasks[user_id] = asyncio.create_task(self._worker(user_id))
