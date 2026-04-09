"""Telegram bot command dispatch and handlers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from claude_telegram.claude.session import UserSession, get_or_create_session
from claude_telegram.telegram.stream import split_text

if TYPE_CHECKING:
    from claude_telegram.config import Config
    from claude_telegram.telegram.client import TelegramClient

VALID_MODELS = frozenset({"opus", "sonnet", "haiku"})
VALID_EFFORTS = frozenset({"low", "medium", "high"})
VALID_THINK_TOGGLES = frozenset({"on", "off"})

HELP_TEXT = """\
*Claude Code Bot*

Send any message to interact with Claude Code.

*Session:*
`/new` — new session
`/interrupt` — stop generation

*Config:*
`/project <path>` — switch directory
`/model <opus|sonnet|haiku>` — switch model
`/effort <low|medium|high>` — reasoning depth
`/think <on|off|last>` — thinking visibility

*Info:*
`/status` — current settings
`/help` — this message\
"""


async def dispatch_command(
    command: str,
    args: str,
    chat_id: int,
    user_id: int,
    telegram: TelegramClient,
    config: Config,
    sessions: dict[int, UserSession],
) -> bool:
    """Handle a bot command. Returns True if the command was recognized."""
    session = get_or_create_session(user_id, sessions, config)

    match command:
        case "/help" | "/start":
            await telegram.send_message(chat_id, HELP_TEXT)

        case "/new":
            await session.reset()
            await telegram.send_message(
                chat_id, "New session. Send a message to begin.",
            )

        case "/interrupt":
            if session.connected:
                try:
                    await session.interrupt()
                    await telegram.send_message(chat_id, "Interrupted.")
                except Exception as exc:
                    await telegram.send_message(
                        chat_id, f"Interrupt failed: `{exc}`",
                    )
            else:
                await telegram.send_message(chat_id, "No active session.")

        case "/project":
            path = args.strip()
            if not path:
                await telegram.send_message(
                    chat_id,
                    f"Current: `{session.project}`\nUsage: `/project <path>`",
                )
            elif os.path.isdir(path):
                session.project = path
                await session.reset()
                await telegram.send_message(
                    chat_id, f"Project: `{path}` (new session)",
                )
            else:
                await telegram.send_message(chat_id, f"Not found: `{path}`")

        case "/model":
            model = args.strip().lower()
            if model in VALID_MODELS:
                session.model = model
                await session.reset()
                await telegram.send_message(
                    chat_id, f"Model: `{model}` (new session)",
                )
            else:
                await telegram.send_message(
                    chat_id,
                    f"Current: `{session.model}`\n"
                    f"Usage: `/model <opus|sonnet|haiku>`",
                )

        case "/effort":
            effort = args.strip().lower()
            if effort in VALID_EFFORTS:
                session.effort = effort
                await telegram.send_message(chat_id, f"Effort: `{effort}`")
            else:
                await telegram.send_message(
                    chat_id,
                    f"Current: `{session.effort}`\n"
                    f"Usage: `/effort <low|medium|high>`",
                )

        case "/think":
            mode = args.strip().lower()
            if mode == "last":
                if session.last_thinking:
                    for chunk in split_text(session.last_thinking, 4000):
                        await telegram.send_message(
                            chat_id, f"```\n{chunk}\n```",
                        )
                else:
                    await telegram.send_message(
                        chat_id, "No thinking from last response.",
                    )
            elif mode in VALID_THINK_TOGGLES:
                session.think_mode = mode
                await telegram.send_message(chat_id, f"Thinking: `{mode}`")
            else:
                await telegram.send_message(
                    chat_id,
                    f"Current: `{session.think_mode}`\n"
                    f"Usage: `/think <on|off|last>`",
                )

        case "/status":
            connected = "yes" if session.connected else "no"
            await telegram.send_message(
                chat_id,
                f"*Status*\n"
                f"Project: `{session.project}`\n"
                f"Model: `{session.model}`\n"
                f"Effort: `{session.effort}`\n"
                f"Thinking: `{session.think_mode}`\n"
                f"Connected: `{connected}`",
            )

        case _:
            return False

    return True
