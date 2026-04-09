"""Application bootstrap."""

from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from claude_telegram.attachments.service import AttachmentService
from claude_telegram.claude.runtime import ClaudeSessionPool
from claude_telegram.config.logging import configure_logging
from claude_telegram.config.settings import AppSettings
from claude_telegram.persistence.database import Database
from claude_telegram.persistence.repositories import PreferencesRepository, QueueRepository, SessionRepository, UpdateRepository
from claude_telegram.sessions.coordinator import SessionCoordinator
from claude_telegram.telegram.draft_api import DraftMessageApi
from claude_telegram.telegram.middleware import AuthorizationMiddleware
from claude_telegram.telegram.polling import TelegramPollingRunner
from claude_telegram.telegram.presenter import TelegramPresenter
from claude_telegram.telegram.router import create_router

log = logging.getLogger(__name__)


class ClaudeTelegramApplication:
    """Own the application's runtime dependencies and lifecycle."""

    def __init__(
        self,
        settings: AppSettings,
        bot: Bot,
        dispatcher: Dispatcher,
        database: Database,
        coordinator: SessionCoordinator,
        polling_runner: TelegramPollingRunner,
    ):
        self.settings = settings
        self.bot = bot
        self.dispatcher = dispatcher
        self.database = database
        self.coordinator = coordinator
        self.polling_runner = polling_runner

    @classmethod
    async def create(cls, settings: AppSettings | None = None) -> "ClaudeTelegramApplication":
        resolved_settings = settings or AppSettings()
        configure_logging(resolved_settings.log_level)

        database = Database(resolved_settings.state_db_path)
        await database.connect()

        session = AiohttpSession(
            api=TelegramAPIServer.from_base(
                resolved_settings.telegram_api_base,
                is_local=True,
            )
        )
        bot = Bot(token=resolved_settings.telegram_bot_token, session=session)
        dispatcher = Dispatcher()

        preferences_repository = PreferencesRepository(database, resolved_settings)
        session_repository = SessionRepository(database)
        queue_repository = QueueRepository(database)
        update_repository = UpdateRepository(database)

        attachment_service = AttachmentService(resolved_settings)
        presenter = TelegramPresenter(
            bot=bot,
            draft_api=DraftMessageApi(
                api_base=resolved_settings.telegram_api_base,
                bot_token=resolved_settings.telegram_bot_token,
            ),
            settings=resolved_settings,
        )
        coordinator = SessionCoordinator(
            bot=bot,
            presenter=presenter,
            attachment_service=attachment_service,
            preferences_repository=preferences_repository,
            session_repository=session_repository,
            queue_repository=queue_repository,
            claude_pool=ClaudeSessionPool(resolved_settings, session_repository),
        )

        router = create_router(coordinator, attachment_service, presenter)
        router.message.middleware(AuthorizationMiddleware(resolved_settings.allowed_user_ids))
        dispatcher.include_router(router)

        polling_runner = TelegramPollingRunner(
            bot=bot,
            dispatcher=dispatcher,
            settings=resolved_settings,
            update_repository=update_repository,
        )

        application = cls(
            settings=resolved_settings,
            bot=bot,
            dispatcher=dispatcher,
            database=database,
            coordinator=coordinator,
            polling_runner=polling_runner,
        )
        await application.coordinator.recover()
        if not resolved_settings.allowed_user_ids:
            log.warning("ALLOWED_USER_IDS is empty. The bot is open to all Telegram users.")
        return application

    async def run(self) -> None:
        me = await self.bot.get_me()
        log.info("Authenticated as @%s", me.username)
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for current_signal in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(current_signal, stop_event.set)

        polling_task = asyncio.create_task(self.polling_runner.run())
        stop_task = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            {polling_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if stop_task in done:
            polling_task.cancel()
            await asyncio.gather(polling_task, return_exceptions=True)
        else:
            await polling_task

    async def close(self) -> None:
        await self.coordinator.shutdown()
        await self.bot.session.close()
        await self.database.close()


async def run_application() -> None:
    application = await ClaudeTelegramApplication.create()
    try:
        await application.run()
    finally:
        await application.close()


def main() -> int:
    asyncio.run(run_application())
    return 0
