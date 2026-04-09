"""Session coordinator tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest import IsolatedAsyncioTestCase

from claude_telegram.claude.events import RunFinished, TextDelta
from claude_telegram.domain.models import ClaudeEffort, InboundMessage, QueueEnqueueResult, UserSessionRecord
from claude_telegram.persistence.database import Database
from claude_telegram.persistence.repositories import PreferencesRepository, QueueRepository, SessionRepository
from claude_telegram.sessions.coordinator import SessionCoordinator
from tests.test_support import configured_settings


class FakeBridge:
    def __init__(self, presenter: "FakePresenter", chat_id: int):
        self.presenter = presenter
        self.chat_id = chat_id
        self.buffer = ""

    async def push_text(self, text: str) -> None:
        self.buffer += text

    async def finalize(self, final_text: str) -> None:
        self.presenter.final_messages.append((self.chat_id, final_text))


@dataclass
class FakePresenter:
    final_messages: list[tuple[int, str]] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    async def send_typing(self, chat_id: int) -> None:
        return None

    def create_stream_bridge(self, chat_id: int) -> FakeBridge:
        return FakeBridge(self, chat_id)

    async def send_tool_status(self, chat_id: int, invocation) -> None:
        return None

    async def send_thinking(self, chat_id: int, thinking_text: str) -> None:
        return None

    async def send_plain(self, chat_id: int, text: str) -> None:
        self.notices.append(text)

    async def send_error(self, chat_id: int, error_message: str) -> None:
        self.notices.append(error_message)


class FakeAttachmentService:
    async def snapshot_outbox(self) -> dict[str, object]:
        return {}

    async def collect_new_artifacts(self, before_snapshot: dict[str, object]) -> list[object]:
        return []

    async def send_artifacts(self, bot, chat_id: int, artifacts: list[object]) -> None:
        return None


class FakeSession:
    def __init__(self, prompt_log: list[str]):
        self._prompt_log = prompt_log

    async def iter_events(self, prompt: str):
        self._prompt_log.append(prompt)
        yield TextDelta(text=f"reply:{prompt}")
        yield RunFinished(total_cost_usd=None)


class FakeClaudePool:
    def __init__(self):
        self.prompt_log: list[str] = []
        self.reset_reasons: list[str] = []

    async def get_or_create(self, preferences, record: UserSessionRecord) -> FakeSession:
        return FakeSession(self.prompt_log)

    async def reset(self, user_id: int, reason: str) -> None:
        self.reset_reasons.append(reason)

    async def interrupt(self, user_id: int) -> bool:
        return False

    def has_active_session(self, user_id: int) -> bool:
        return False

    async def shutdown(self) -> None:
        return None


class SessionCoordinatorTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._settings_context = configured_settings()
        self.settings = self._settings_context.__enter__()
        self.database = Database(self.settings.state_db_path)
        await self.database.connect()
        self.preferences_repository = PreferencesRepository(self.database, self.settings)
        self.session_repository = SessionRepository(self.database)
        self.queue_repository = QueueRepository(self.database)
        self.presenter = FakePresenter()
        self.claude_pool = FakeClaudePool()
        self.coordinator = SessionCoordinator(
            bot=None,
            presenter=self.presenter,
            attachment_service=FakeAttachmentService(),
            preferences_repository=self.preferences_repository,
            session_repository=self.session_repository,
            queue_repository=self.queue_repository,
            claude_pool=self.claude_pool,
        )

    async def asyncTearDown(self) -> None:
        await self.coordinator.shutdown()
        await self.database.close()
        self._settings_context.__exit__(None, None, None)

    async def test_enqueue_message_processes_multiple_prompts_in_order(self) -> None:
        first = InboundMessage(chat_id=99, user_id=1, source_message_id=1, text="first")
        second = InboundMessage(chat_id=99, user_id=1, source_message_id=2, text="second")

        first_result = await self.coordinator.enqueue_message(first)
        second_result = await self.coordinator.enqueue_message(second)

        self.assertTrue(first_result.created)
        self.assertGreaterEqual(second_result.requests_ahead, 1)

        for _ in range(20):
            if len(self.presenter.final_messages) == 2:
                break
            await asyncio.sleep(0.01)

        self.assertEqual(self.claude_pool.prompt_log, ["first", "second"])
        self.assertEqual(
            self.presenter.final_messages,
            [(99, "reply:first"), (99, "reply:second")],
        )

    async def test_update_effort_resets_session(self) -> None:
        await self.coordinator.update_effort(1, ClaudeEffort.LOW)
        self.assertIn("effort changed", self.claude_pool.reset_reasons)

