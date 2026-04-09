"""Aiogram routers and handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from claude_telegram.attachments.service import AttachmentService
from claude_telegram.sessions.coordinator import SessionCoordinator
from claude_telegram.telegram.commands import parse_effort, parse_model, parse_thinking_mode, resolve_project_path
from claude_telegram.telegram.presenter import TelegramPresenter


def create_router(
    coordinator: SessionCoordinator,
    attachment_service: AttachmentService,
    presenter: TelegramPresenter,
) -> Router:
    """Build the application router."""
    router = Router(name="claude-telegram")

    @router.message(CommandStart())
    @router.message(Command("help"))
    async def handle_help(message: Message) -> None:
        if message.chat is None:
            return
        await presenter.send_help(message.chat.id)

    @router.message(Command("new"))
    async def handle_new_session(message: Message) -> None:
        if message.chat is None or message.from_user is None:
            return
        await coordinator.reset_session(message.from_user.id, reason="new session requested")
        await presenter.send_plain(message.chat.id, "New session. Send a message to begin.")

    @router.message(Command("interrupt"))
    async def handle_interrupt(message: Message) -> None:
        if message.chat is None or message.from_user is None:
            return
        interrupted = await coordinator.interrupt(message.from_user.id)
        await presenter.send_plain(
            message.chat.id,
            "Interrupted." if interrupted else "No active session.",
        )

    @router.message(Command("project"))
    async def handle_project(message: Message, command: CommandObject) -> None:
        if message.chat is None or message.from_user is None:
            return
        if not command.args:
            preferences = await coordinator.get_preferences(message.from_user.id)
            await presenter.send_html_message(
                message.chat.id,
                f"Current: <code>{preferences.project}</code><br/>Usage: <code>/project &lt;path&gt;</code>",
            )
            return
        project = resolve_project_path(command.args)
        if project is None:
            await presenter.send_html_message(
                message.chat.id,
                f"Not found: <code>{command.args}</code>",
            )
            return
        await coordinator.update_project(message.from_user.id, project)
        await presenter.send_html_message(
            message.chat.id,
            f"Project: <code>{project}</code> (new session)",
        )

    @router.message(Command("model"))
    async def handle_model(message: Message, command: CommandObject) -> None:
        if message.chat is None or message.from_user is None:
            return
        model = parse_model(command.args or "")
        if model is None:
            preferences = await coordinator.get_preferences(message.from_user.id)
            await presenter.send_html_message(
                message.chat.id,
                "Current: "
                f"<code>{preferences.model.value}</code><br/>"
                "Usage: <code>/model &lt;opus|sonnet|haiku&gt;</code>",
            )
            return
        await coordinator.update_model(message.from_user.id, model)
        await presenter.send_html_message(
            message.chat.id,
            f"Model: <code>{model.value}</code> (new session)",
        )

    @router.message(Command("effort"))
    async def handle_effort(message: Message, command: CommandObject) -> None:
        if message.chat is None or message.from_user is None:
            return
        effort = parse_effort(command.args or "")
        if effort is None:
            preferences = await coordinator.get_preferences(message.from_user.id)
            await presenter.send_html_message(
                message.chat.id,
                "Current: "
                f"<code>{preferences.effort.value}</code><br/>"
                "Usage: <code>/effort &lt;low|medium|high&gt;</code>",
            )
            return
        await coordinator.update_effort(message.from_user.id, effort)
        await presenter.send_html_message(
            message.chat.id,
            f"Effort: <code>{effort.value}</code> (new session)",
        )

    @router.message(Command("think"))
    async def handle_think(message: Message, command: CommandObject) -> None:
        if message.chat is None or message.from_user is None:
            return
        argument = (command.args or "").strip().lower()
        if argument == "last":
            preferences = await coordinator.get_preferences(message.from_user.id)
            if preferences.last_thinking:
                await presenter.send_thinking(message.chat.id, preferences.last_thinking)
            else:
                await presenter.send_plain(message.chat.id, "No thinking from last response.")
            return
        think_mode = parse_thinking_mode(argument)
        if think_mode is None:
            preferences = await coordinator.get_preferences(message.from_user.id)
            await presenter.send_html_message(
                message.chat.id,
                "Current: "
                f"<code>{preferences.think_mode.value}</code><br/>"
                "Usage: <code>/think &lt;on|off|last&gt;</code>",
            )
            return
        await coordinator.update_thinking_mode(message.from_user.id, think_mode)
        await presenter.send_html_message(
            message.chat.id,
            f"Thinking: <code>{think_mode.value}</code>",
        )

    @router.message(Command("status"))
    async def handle_status(message: Message) -> None:
        if message.chat is None or message.from_user is None:
            return
        await presenter.send_status(
            message.chat.id,
            await coordinator.get_status(message.from_user.id),
        )

    @router.message(F.text.startswith("/"))
    async def handle_unknown_command(message: Message) -> None:
        if message.chat is None or not message.text:
            return
        command_name = message.text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
        await presenter.send_unknown_command(message.chat.id, command_name)

    @router.message()
    async def handle_inbound_message(message: Message, bot) -> None:
        inbound = await attachment_service.extract_message(bot, message)
        if inbound is None:
            return
        result = await coordinator.enqueue_message(inbound)
        if result.created and result.requests_ahead > 0:
            await presenter.send_queue_notice(message.chat.id, result.requests_ahead)

    return router

