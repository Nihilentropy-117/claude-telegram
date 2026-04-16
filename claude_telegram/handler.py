"""Main message handler: query Claude and stream the response to Telegram."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)

from claude_telegram.claude.session import UserSession, get_or_create_session
from claude_telegram.claude.tools import format_tool_status
from claude_telegram.telegram.files import deliver_outbox
from claude_telegram.telegram.stream import StreamBridge, split_text

if TYPE_CHECKING:
    from claude_telegram.config import Config
    from claude_telegram.telegram.client import TelegramClient

log = logging.getLogger(__name__)


async def handle_message(
    prompt: str,
    chat_id: int,
    user_id: int,
    telegram: TelegramClient,
    config: Config,
    sessions: dict[int, UserSession],
) -> None:
    """Send a prompt to Claude and stream the response back to Telegram."""
    session = get_or_create_session(user_id, sessions, config)

    if session.busy:
        await telegram.send_message(chat_id, "Still working. Hold on.")
        return

    session.busy = True
    try:
        await telegram.send_chat_action(chat_id)
        client = await session.get_client(config)
        bridge = StreamBridge(
            telegram, chat_id,
            interval_seconds=config.stream_interval_ms / 1000.0,
        )

        await client.query(prompt)

        text_parts: list[str] = []
        thinking_parts: list[str] = []

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                        await bridge.push(block.text)
                    elif isinstance(block, ThinkingBlock):
                        thinking_parts.append(block.thinking)
                    elif isinstance(block, ToolUseBlock):
                        log.info("Tool: %s", block.name)
                        inputs = getattr(block, "input", {}) or {}
                        await telegram.send_message(
                            chat_id, format_tool_status(block.name, inputs),
                        )

            elif isinstance(message, ResultMessage):
                if message.total_cost_usd:
                    log.info("Cost: $%.4f", message.total_cost_usd)
                break

        session.last_thinking = "\n".join(thinking_parts)
        full_text = "".join(text_parts)

        if session.think_mode == "on" and session.last_thinking:
            for chunk in split_text(session.last_thinking, 4000):
                await telegram.send_message(
                    chat_id, f"\U0001f4ad _{chunk}_",
                )

        await bridge.finalize(full_text)
        await deliver_outbox(telegram, chat_id)

    except Exception as exc:
        log.exception("Error handling message for user %d", user_id)
        await telegram.send_message(chat_id, f"\u26a0\ufe0f Error: `{exc}`")
        await session.destroy_client()
    finally:
        session.busy = False
