"""Telegram-facing formatting and streaming."""

from __future__ import annotations

import html
import logging
import os
import time
from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramAPIError

from claude_telegram.config.settings import AppSettings
from claude_telegram.domain.models import ToolInvocation, UserStatus
from claude_telegram.telegram.draft_api import DraftMessageApi

log = logging.getLogger(__name__)

HELP_HTML = """<b>Claude Telegram Bot</b>

Send any message to interact with Claude Code.

<b>Session</b>
/new — new session
/interrupt — stop generation

<b>Config</b>
/project &lt;path&gt; — switch directory
/model &lt;opus|sonnet|haiku&gt; — switch model
/effort &lt;low|medium|high&gt; — reasoning depth
/think &lt;on|off|last&gt; — thinking visibility

<b>Info</b>
/status — current settings
/help — this message"""


class TelegramPresenter:
    """Send consistently formatted Telegram output."""

    def __init__(self, bot: Bot, draft_api: DraftMessageApi, settings: AppSettings):
        self._bot = bot
        self._draft_api = draft_api
        self._settings = settings

    async def send_help(self, chat_id: int) -> None:
        await self._send_html(chat_id, HELP_HTML)

    async def send_unknown_command(self, chat_id: int, command_name: str) -> None:
        await self._send_html(
            chat_id,
            f"Unknown command: <code>{html.escape(command_name)}</code><br/>Try /help",
        )

    async def send_plain(self, chat_id: int, text: str) -> None:
        for chunk in self.chunk_text(text or "(empty response)", 4096):
            await self._bot.send_message(chat_id=chat_id, text=chunk)

    async def send_html_message(self, chat_id: int, html_text: str) -> None:
        await self._send_html(chat_id, html_text)

    async def send_queue_notice(self, chat_id: int, requests_ahead: int) -> None:
        plural = "request" if requests_ahead == 1 else "requests"
        await self._send_html(
            chat_id,
            f"Queued. <b>{requests_ahead}</b> {plural} ahead of this one.",
        )

    async def send_status(self, chat_id: int, status: UserStatus) -> None:
        connected = "yes" if status.connected else "no"
        await self._send_html(
            chat_id,
            "<b>Status</b><br/>"
            f"Project: <code>{html.escape(status.preferences.project)}</code><br/>"
            f"Model: <code>{status.preferences.model.value}</code><br/>"
            f"Effort: <code>{status.preferences.effort.value}</code><br/>"
            f"Thinking: <code>{status.preferences.think_mode.value}</code><br/>"
            f"Connected: <code>{connected}</code><br/>"
            f"Queued: <code>{status.queued_requests}</code>",
        )

    async def send_thinking(self, chat_id: int, thinking_text: str) -> None:
        for chunk in self.chunk_text(thinking_text, 4000):
            await self.send_plain(chat_id, f"Thinking:\n{chunk}")

    async def send_tool_status(self, chat_id: int, invocation: ToolInvocation) -> None:
        if invocation.name == "Bash":
            command = invocation.input_payload.get("command", "")
            message = (
                "<b>Bash</b>\n"
                f"<pre>{html.escape(self._truncate(str(command), 400))}</pre>"
            )
        elif invocation.name == "Read":
            path = invocation.input_payload.get("file_path", "")
            message = f"<b>Read</b> <code>{html.escape(self._truncate(str(path), 200))}</code>"
        elif invocation.name in {"Write", "Edit"}:
            path = invocation.input_payload.get("file_path", "")
            message = f"<b>{invocation.name}</b> <code>{html.escape(self._truncate(str(path), 200))}</code>"
        elif invocation.name == "Glob":
            pattern = invocation.input_payload.get("pattern", "")
            message = f"<b>Glob</b> <code>{html.escape(self._truncate(str(pattern), 200))}</code>"
        elif invocation.name == "Grep":
            pattern = invocation.input_payload.get("pattern", "")
            path = invocation.input_payload.get("path", "")
            location = f" in <code>{html.escape(self._truncate(str(path), 100))}</code>" if path else ""
            message = (
                f"<b>Grep</b> <code>{html.escape(self._truncate(str(pattern), 200))}</code>{location}"
            )
        else:
            message = f"<b>{html.escape(invocation.name)}</b>"
        await self._send_html(chat_id, message)

    async def send_error(self, chat_id: int, error_message: str) -> None:
        await self._send_html(
            chat_id,
            f"⚠️ Error: <code>{html.escape(error_message)}</code>",
        )

    async def send_typing(self, chat_id: int) -> None:
        await self._bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    def create_stream_bridge(self, chat_id: int) -> "StreamBridge":
        return StreamBridge(self, chat_id, self._settings.stream_interval_ms / 1000.0)

    async def push_draft(self, chat_id: int, draft_id: int, text: str) -> None:
        try:
            await self._draft_api.send_draft(chat_id, draft_id, text)
        except Exception as exc:
            log.warning("Draft update failed for chat %s.", chat_id, exc_info=exc)

    async def _send_html(self, chat_id: int, html_text: str) -> None:
        await self._bot.send_message(
            chat_id=chat_id,
            text=html_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    @staticmethod
    def _truncate(value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value
        return value[:max_length] + "…"

    @staticmethod
    def chunk_text(text: str, max_length: int) -> list[str]:
        if len(text) <= max_length:
            return [text]
        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break
            cut = remaining.rfind("\n", 0, max_length)
            if cut < max_length // 2:
                cut = max_length
            chunks.append(remaining[:cut])
            remaining = remaining[cut:].lstrip("\n")
        return chunks


@dataclass(slots=True)
class StreamBridge:
    """Throttle draft updates while preserving the final full response."""

    presenter: TelegramPresenter
    chat_id: int
    interval_seconds: float
    draft_id: int = 0
    buffer: str = ""
    last_push_at: float = 0.0

    def __post_init__(self) -> None:
        self.draft_id = int.from_bytes(os.urandom(8), "big") >> 1 or 1

    async def push_text(self, text: str) -> None:
        self.buffer += text
        now = time.monotonic()
        if now - self.last_push_at >= self.interval_seconds:
            await self._push()

    async def finalize(self, final_text: str) -> None:
        await self.presenter.send_plain(self.chat_id, final_text or "(empty response)")

    async def _push(self) -> None:
        if not self.buffer.strip():
            return
        await self.presenter.push_draft(
            self.chat_id,
            self.draft_id,
            self.buffer[-4096:] if len(self.buffer) > 4096 else self.buffer,
        )
        self.last_push_at = time.monotonic()
