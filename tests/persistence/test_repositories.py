"""Repository tests."""

from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from claude_telegram.domain.models import PromptStatus
from claude_telegram.persistence.database import Database
from claude_telegram.persistence.repositories import PreferencesRepository, QueueRepository, SessionRepository, UpdateRepository
from tests.test_support import configured_settings


class RepositoryTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._settings_context = configured_settings()
        self.settings = self._settings_context.__enter__()
        self.database = Database(self.settings.state_db_path)
        await self.database.connect()
        self.preferences_repository = PreferencesRepository(self.database, self.settings)
        self.queue_repository = QueueRepository(self.database)
        self.session_repository = SessionRepository(self.database)
        self.update_repository = UpdateRepository(self.database)

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self._settings_context.__exit__(None, None, None)

    async def test_get_or_create_preferences_returns_defaults(self) -> None:
        preferences = await self.preferences_repository.get_or_create(123)
        self.assertEqual(preferences.project, "/projects")
        self.assertEqual(preferences.model.value, "sonnet")

    async def test_queue_enqueue_is_idempotent_for_same_message(self) -> None:
        first = await self.queue_repository.enqueue(1, 99, "hello", 10)
        second = await self.queue_repository.enqueue(1, 99, "hello", 10)
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.prompt.prompt_id, second.prompt.prompt_id)

    async def test_stale_running_jobs_are_marked_failed(self) -> None:
        queued = await self.queue_repository.enqueue(1, 99, "hello", 10)
        await self.queue_repository.mark_running(queued.prompt.prompt_id)
        stale_users = await self.queue_repository.mark_stale_running_jobs_failed("restart")
        prompt = await self.queue_repository.get_by_id(queued.prompt.prompt_id)
        self.assertEqual(stale_users, [1])
        self.assertEqual(prompt.status, PromptStatus.FAILED)

    async def test_processed_update_offset_advances(self) -> None:
        self.assertIsNone(await self.update_repository.next_offset())
        await self.update_repository.mark_processed(42)
        self.assertEqual(await self.update_repository.next_offset(), 43)

