"""Polling loop and application lifecycle."""

from __future__ import annotations

import asyncio
import logging
import signal

import httpx

from claude_telegram.claude.session import UserSession
from claude_telegram.commands import dispatch_command
from claude_telegram.config import Config
from claude_telegram.handler import handle_message
from claude_telegram.telegram.client import TelegramClient
from claude_telegram.telegram.extract import extract_prompt

log = logging.getLogger(__name__)


def _on_task_done(task: asyncio.Task[None]) -> None:
    """Log unhandled exceptions from fire-and-forget message handler tasks."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("Unhandled exception in background task: %s", exc, exc_info=exc)


async def poll(telegram: TelegramClient, config: Config) -> None:
    """Long-poll Telegram for updates and dispatch messages."""
    sessions: dict[int, UserSession] = {}
    offset: int | None = None

    log.info("Polling for updates...")

    while True:
        try:
            updates = await telegram.get_updates(offset=offset, timeout=30)
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            continue
        except Exception as exc:
            log.error("Polling error: %s", exc)
            await asyncio.sleep(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message")
            if not message:
                continue

            user_id: int | None = message.get("from", {}).get("id")
            chat_id: int | None = message.get("chat", {}).get("id")
            if not user_id or not chat_id:
                continue

            if (
                config.allowed_user_ids
                and user_id not in config.allowed_user_ids
            ):
                log.warning("Unauthorized user %d", user_id)
                continue

            # Command dispatch (text messages starting with /)
            text = message.get("text", "")
            if text.startswith("/"):
                tokens = text.split(maxsplit=1)
                command = tokens[0].lower().split("@")[0]  # Strip @botname
                args = tokens[1] if len(tokens) > 1 else ""
                handled = await dispatch_command(
                    command, args, chat_id, user_id,
                    telegram, config, sessions,
                )
                if not handled:
                    await telegram.send_message(
                        chat_id, f"Unknown command: `{command}`\nTry /help",
                    )
                continue

            # Extract prompt from any message type and handle asynchronously
            prompt = await extract_prompt(message, telegram)
            if prompt:
                task = asyncio.create_task(
                    handle_message(
                        prompt, chat_id, user_id,
                        telegram, config, sessions,
                    ),
                )
                task.add_done_callback(_on_task_done)


async def run() -> None:
    """Application entry point: configure, authenticate, and start polling."""
    config = Config.from_env()

    async with httpx.AsyncClient() as http:
        telegram = TelegramClient(
            config.telegram_token, http, config.telegram_api_base,
        )

        me = await telegram.get_me()
        bot_name = me.get("result", {}).get("username", "unknown")
        log.info("Authenticated as @%s", bot_name)

        # NOTE: The original code used `sys.exit(0)` inside the signal handler,
        # which raises SystemExit in the async context and can leave resources
        # (httpx client, SDK connections) uncleaned. An asyncio.Event allows
        # the httpx context manager to close properly on shutdown.
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        poll_task = asyncio.create_task(poll(telegram, config))
        await stop.wait()

        log.info("Shutting down...")
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass

    log.info("Shutdown complete.")
