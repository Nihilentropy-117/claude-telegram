#!/usr/bin/env python3
"""
Claude Code Telegram Bot (SDK version)
Uses claude-agent-sdk ClaudeSDKClient for persistent sessions with typed streaming.
Raw httpx against Telegram API. No framework.
"""

import asyncio
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("claude-tg")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    telegram_token: str = ""
    allowed_user_ids: list[int] = field(default_factory=list)
    default_project: str = "/projects"
    default_model: str = "sonnet"
    default_effort: str = "high"
    max_turns: int = 10
    stream_interval_ms: int = 150

    @classmethod
    def from_env(cls) -> "Config":
        c = cls()
        c.telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
        raw_ids = os.environ.get("ALLOWED_USER_IDS", "")
        c.allowed_user_ids = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]
        c.default_project = os.environ.get("DEFAULT_PROJECT", c.default_project)
        c.default_model = os.environ.get("DEFAULT_MODEL", c.default_model)
        c.default_effort = os.environ.get("DEFAULT_EFFORT", c.default_effort)
        c.max_turns = int(os.environ.get("MAX_TURNS", c.max_turns))
        return c


# ---------------------------------------------------------------------------
# Per-user session state
# ---------------------------------------------------------------------------

@dataclass
class UserState:
    project: str = ""
    model: str = "sonnet"
    effort: str = "high"
    think: str = "off"           # off | on | last
    last_thinking: str = ""
    busy: bool = False
    client: ClaudeSDKClient | None = None

    def _model_env(self) -> str:
        if self.model == "haiku":
            return "claude-haiku-4-5"
        return f"claude-{self.model}-4-6"

    def _build_options(self, config: Config) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            cwd=self.project,
            max_turns=config.max_turns,
            system_prompt=(
                "You are Claude Code, accessed via Telegram. "
                "Keep responses concise for mobile reading. "
                "Use markdown formatting compatible with Telegram. "
                "You have full root access in a sandboxed Docker container. "
                "Install any packages you need freely — pip uses a persistent venv at /venv, "
                "apt cache is persistent. See ~/.claude/CLAUDE.md for full details."
            ),
            env={
                "ANTHROPIC_MODEL": self._model_env(),
                "IS_SANDBOX": "1",
            },
        )

    async def get_client(self, config: Config) -> ClaudeSDKClient:
        if self.client is None:
            options = self._build_options(config)
            self.client = ClaudeSDKClient(options=options)
            await self.client.connect()
            log.info("SDK client connected (cwd=%s, model=%s)", self.project, self.model)
        return self.client

    async def destroy_client(self):
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None

    async def new_session(self, config: Config):
        await self.destroy_client()


# ---------------------------------------------------------------------------
# Telegram API wrapper
# ---------------------------------------------------------------------------

class TelegramAPI:
    def __init__(self, token: str, client: httpx.AsyncClient):
        self.base = f"https://api.telegram.org/bot{token}"
        self.client = client

    async def call(self, method: str, **params) -> dict:
        http_timeout = params.pop("_http_timeout", 60)
        params = {k: v for k, v in params.items() if v is not None}
        resp = await self.client.post(f"{self.base}/{method}", json=params, timeout=http_timeout)
        data = resp.json()
        if not data.get("ok"):
            log.error("Telegram API error on %s: %s", method, data)
        return data

    async def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict]:
        data = await self.call("getUpdates", offset=offset, timeout=timeout,
                               _http_timeout=timeout + 10)
        return data.get("result", [])

    async def send_message(self, chat_id: int, text: str, **kwargs) -> dict:
        return await self.call("sendMessage", chat_id=chat_id, text=text,
                               parse_mode="Markdown", **kwargs)

    async def send_draft(self, chat_id: int, draft_id: int, text: str, **kwargs) -> dict:
        return await self.call("sendMessageDraft", chat_id=chat_id,
                               random_id=draft_id, text=text, **kwargs)

    async def send_action(self, chat_id: int, action: str = "typing") -> dict:
        return await self.call("sendChatAction", chat_id=chat_id, action=action)

    async def get_me(self) -> dict:
        return await self.call("getMe")

    async def get_file(self, file_id: str) -> dict:
        return await self.call("getFile", file_id=file_id)

    async def download_file(self, file_path: str) -> bytes:
        """Download a file from Telegram servers by its file_path."""
        url = f"https://api.telegram.org/file/bot{self.base.split('/bot')[1]}/{file_path}"
        resp = await self.client.get(url, timeout=120)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# Streaming bridge: SDK messages → Telegram sendMessageDraft
# ---------------------------------------------------------------------------

class StreamBridge:
    def __init__(self, tg: TelegramAPI, chat_id: int, config: Config):
        self.tg = tg
        self.chat_id = chat_id
        self.draft_id = int.from_bytes(os.urandom(8), 'big') >> 1 or 1
        self.buffer = ""
        self.last_push = 0.0
        self.interval = config.stream_interval_ms / 1000.0

    async def push_text(self, chunk: str):
        self.buffer += chunk
        now = time.monotonic()
        if now - self.last_push >= self.interval:
            await self._push_draft()

    async def _push_draft(self):
        if not self.buffer.strip():
            return
        text = self.buffer[-4096:] if len(self.buffer) > 4096 else self.buffer
        await self.tg.send_draft(self.chat_id, self.draft_id, text)
        self.last_push = time.monotonic()

    async def finalize(self, full_text: str):
        if not full_text.strip():
            full_text = "_(empty response)_"
        for chunk in self._chunk_text(full_text, 4096):
            await self.tg.send_message(self.chat_id, chunk)

    @staticmethod
    def _chunk_text(text: str, max_len: int) -> list[str]:
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            cut = text.rfind("\n", 0, max_len)
            if cut == -1 or cut < max_len // 2:
                cut = max_len
            chunks.append(text[:cut])
            text = text[cut:].lstrip("\n")
        return chunks


# ---------------------------------------------------------------------------
# Telegram message → prompt extraction (text, files, location, contact)
# ---------------------------------------------------------------------------

TEMP_DIR = Path("/temp")

async def extract_message(msg: dict, tg: TelegramAPI) -> str | None:
    """
    Extract a prompt string from any Telegram message type.
    Downloads files to /temp, converts location/contact to text.
    Returns None if the message has no usable content.
    """
    parts = []

    # Caption or text body
    caption = msg.get("caption", "")
    text = msg.get("text", "")
    user_text = caption or text

    if user_text:
        parts.append(user_text)

    # --- File-bearing message types ---
    file_id = None
    file_name = None
    file_desc = None

    if "document" in msg:
        doc = msg["document"]
        file_id = doc["file_id"]
        file_name = doc.get("file_name", f"document_{file_id[:8]}")
        file_desc = f"document ({doc.get('mime_type', 'unknown type')})"

    elif "photo" in msg:
        # Telegram sends multiple sizes; pick the largest
        photo = msg["photo"][-1]
        file_id = photo["file_id"]
        file_name = f"photo_{file_id[:8]}.jpg"
        file_desc = f"photo ({photo.get('width', '?')}x{photo.get('height', '?')})"

    elif "voice" in msg:
        voice = msg["voice"]
        file_id = voice["file_id"]
        file_name = f"voice_{file_id[:8]}.ogg"
        file_desc = f"voice message ({voice.get('duration', '?')}s)"

    elif "audio" in msg:
        audio = msg["audio"]
        file_id = audio["file_id"]
        file_name = audio.get("file_name", f"audio_{file_id[:8]}.mp3")
        performer = audio.get("performer", "")
        title = audio.get("title", "")
        label = f"{performer} - {title}".strip(" -") if (performer or title) else file_name
        file_desc = f"audio file: {label} ({audio.get('duration', '?')}s)"

    elif "video" in msg:
        video = msg["video"]
        file_id = video["file_id"]
        file_name = video.get("file_name", f"video_{file_id[:8]}.mp4")
        file_desc = f"video ({video.get('width', '?')}x{video.get('height', '?')}, {video.get('duration', '?')}s)"

    # Download file if present
    if file_id:
        try:
            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            result = await tg.get_file(file_id)
            tg_path = result.get("result", {}).get("file_path", "")
            if tg_path:
                data = await tg.download_file(tg_path)
                # Use original extension from Telegram path if our name lacks one
                if "." in tg_path and "." not in file_name.rsplit("/", 1)[-1]:
                    ext = tg_path.rsplit(".", 1)[-1]
                    file_name = f"{file_name}.{ext}"
                local_path = TEMP_DIR / file_name
                local_path.write_bytes(data)
                parts.append(f"[Attached {file_desc}, saved to {local_path}]")
                log.info("Downloaded %s → %s (%d bytes)", file_desc, local_path, len(data))
            else:
                parts.append(f"[Attached {file_desc}, but download failed]")
        except Exception as e:
            log.error("File download failed: %s", e)
            parts.append(f"[Attached {file_desc}, download error: {e}]")

    # --- Non-file types ---
    if "location" in msg:
        loc = msg["location"]
        lat, lon = loc["latitude"], loc["longitude"]
        parts.append(f"[User shared a location: {lat}, {lon}]")

    if "contact" in msg:
        contact = msg["contact"]
        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        phone = contact.get("phone_number", "unknown")
        parts.append(f"[User shared a contact: {name}, phone: {phone}]")

    if not parts:
        return None

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

HELP_TEXT = """*Claude Code Bot (SDK)*

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
`/help` — this message"""


async def handle_command(
    cmd: str, args: str, chat_id: int, user_id: int,
    tg: TelegramAPI, config: Config, states: dict[int, UserState],
) -> bool:
    state = states.setdefault(user_id, UserState(project=config.default_project,
                                                  model=config.default_model,
                                                  effort=config.default_effort))
    match cmd:
        case "/help" | "/start":
            await tg.send_message(chat_id, HELP_TEXT)

        case "/new":
            await state.new_session(config)
            await tg.send_message(chat_id, "New session. Send a message to begin.")

        case "/interrupt":
            if state.client:
                try:
                    await state.client.interrupt()
                    await tg.send_message(chat_id, "Interrupted.")
                except Exception as e:
                    await tg.send_message(chat_id, f"Interrupt failed: `{e}`")
            else:
                await tg.send_message(chat_id, "No active session.")

        case "/project":
            path = args.strip()
            if not path:
                await tg.send_message(chat_id, f"Current: `{state.project}`\nUsage: `/project <path>`")
            elif os.path.isdir(path):
                state.project = path
                await state.new_session(config)
                await tg.send_message(chat_id, f"Project: `{path}` (new session)")
            else:
                await tg.send_message(chat_id, f"Not found: `{path}`")

        case "/model":
            m = args.strip().lower()
            if m in ("opus", "sonnet", "haiku"):
                state.model = m
                await state.new_session(config)
                await tg.send_message(chat_id, f"Model: `{m}` (new session)")
            else:
                await tg.send_message(chat_id, f"Current: `{state.model}`\nUsage: `/model <opus|sonnet|haiku>`")

        case "/effort":
            e = args.strip().lower()
            if e in ("low", "medium", "high"):
                state.effort = e
                await tg.send_message(chat_id, f"Effort: `{e}`")
            else:
                await tg.send_message(chat_id, f"Current: `{state.effort}`\nUsage: `/effort <low|medium|high>`")

        case "/think":
            t = args.strip().lower()
            if t == "last":
                if state.last_thinking:
                    for chunk in StreamBridge._chunk_text(state.last_thinking, 4000):
                        await tg.send_message(chat_id, f"```\n{chunk}\n```")
                else:
                    await tg.send_message(chat_id, "No thinking from last response.")
            elif t in ("on", "off"):
                state.think = t
                await tg.send_message(chat_id, f"Thinking: `{t}`")
            else:
                await tg.send_message(chat_id, f"Current: `{state.think}`\nUsage: `/think <on|off|last>`")

        case "/status":
            connected = "yes" if state.client else "no"
            await tg.send_message(chat_id,
                f"*Status*\n"
                f"Project: `{state.project}`\n"
                f"Model: `{state.model}`\n"
                f"Effort: `{state.effort}`\n"
                f"Thinking: `{state.think}`\n"
                f"Connected: `{connected}`")

        case _:
            return False

    return True


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------

async def handle_message(
    text: str, chat_id: int, user_id: int,
    tg: TelegramAPI, config: Config, states: dict[int, UserState],
):
    state = states.setdefault(user_id, UserState(project=config.default_project,
                                                  model=config.default_model,
                                                  effort=config.default_effort))
    if state.busy:
        await tg.send_message(chat_id, "Still working. Hold on.")
        return

    state.busy = True
    try:
        await tg.send_action(chat_id)
        client = await state.get_client(config)
        bridge = StreamBridge(tg, chat_id, config)

        await client.query(text)

        full_text_parts = []
        thinking_parts = []
        tool_uses = []

        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        full_text_parts.append(block.text)
                        await bridge.push_text(block.text)
                    elif isinstance(block, ThinkingBlock):
                        thinking_parts.append(block.thinking)
                    elif isinstance(block, ToolUseBlock):
                        tool_uses.append(block.name)

            elif isinstance(msg, ResultMessage):
                if msg.total_cost_usd:
                    log.info("Cost: $%.4f", msg.total_cost_usd)
                break

        state.last_thinking = "\n".join(thinking_parts)
        full_text = "".join(full_text_parts)

        if state.think == "on" and state.last_thinking:
            for chunk in StreamBridge._chunk_text(state.last_thinking, 4000):
                await tg.send_message(chat_id, f"💭 _{chunk}_")

        if tool_uses:
            unique_tools = ", ".join(f"`{t}`" for t in dict.fromkeys(tool_uses))
            full_text += f"\n\n_Tools: {unique_tools}_"

        await bridge.finalize(full_text)

    except Exception as e:
        log.exception("Error handling message")
        await tg.send_message(chat_id, f"⚠️ Error: `{e}`")
        await state.destroy_client()
    finally:
        state.busy = False


# ---------------------------------------------------------------------------
# Polling loop
# ---------------------------------------------------------------------------

async def poll_loop(tg: TelegramAPI, config: Config):
    states: dict[int, UserState] = {}
    offset = None

    log.info("Bot started. Polling for updates...")

    while True:
        try:
            updates = await tg.get_updates(offset=offset, timeout=30)
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            continue
        except Exception as e:
            log.error("Polling error: %s", e)
            await asyncio.sleep(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message")
            if not msg:
                continue

            user_id = msg.get("from", {}).get("id")
            chat_id = msg.get("chat", {}).get("id")

            if not user_id or not chat_id:
                continue

            if config.allowed_user_ids and user_id not in config.allowed_user_ids:
                log.warning("Unauthorized user %s", user_id)
                continue

            # Check for commands first (text-only)
            text = msg.get("text", "")
            if text.startswith("/"):
                parts = text.split(maxsplit=1)
                cmd = parts[0].lower().split("@")[0]
                args = parts[1] if len(parts) > 1 else ""
                handled = await handle_command(cmd, args, chat_id, user_id, tg, config, states)
                if not handled:
                    await tg.send_message(chat_id, f"Unknown command: `{cmd}`\nTry /help")
                continue

            # Extract prompt from any message type (text, file, location, etc.)
            prompt = await extract_message(msg, tg)
            if prompt:
                asyncio.create_task(
                    handle_message(prompt, chat_id, user_id, tg, config, states)
                )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main():
    config = Config.from_env()
    if not config.telegram_token:
        log.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)
    if not config.allowed_user_ids:
        log.warning("ALLOWED_USER_IDS not set — bot is open to everyone!")

    async with httpx.AsyncClient() as http_client:
        tg = TelegramAPI(config.telegram_token, http_client)

        me = await tg.get_me()
        bot_name = me.get("result", {}).get("username", "unknown")
        log.info("Authenticated as @%s", bot_name)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: sys.exit(0))

        await poll_loop(tg, config)


if __name__ == "__main__":
    asyncio.run(main())
