# Claude Code Telegram Bot

Stream Claude Code responses to Telegram in real-time via `sendMessageDraft` (Bot API 9.5).

Built with raw `httpx` against the Telegram Bot API and `claude-agent-sdk` for Claude Code sessions. No frameworks.

## Features

- **Real-time streaming** — responses stream live via Telegram draft messages
- **File exchange** — send files to Claude, receive files back via `/temp/outbox/`
- **Tool visualization** — see tool invocations (Bash, Read, Write, Grep, etc.) as they happen
- **Per-user sessions** — independent Claude Code sessions with persistent state
- **Configurable** — switch models, effort levels, and projects on the fly
- **Thinking mode** — optionally view Claude's extended thinking

## Setup

1. **Create a bot** via [@BotFather](https://t.me/BotFather). Enable streaming in BotFather settings.

2. **Get your user ID** from [@userinfobot](https://t.me/userinfobot).

3. **Configure:**
   ```bash
   cp .env.example .env
   # Edit .env with your token, user ID, and API key
   ```

4. **Deploy:**
   ```bash
   docker compose up -d --build
   ```

5. **Mount your projects** by editing `docker-compose.yml` volumes. The default maps `./claude/projects` to `/projects` inside the container.

## Commands

| Command | Description |
|---|---|
| `/new` | Start a new session |
| `/interrupt` | Stop current generation |
| `/project <path>` | Switch working directory (container paths) |
| `/model <opus\|sonnet\|haiku>` | Switch model |
| `/effort <low\|medium\|high>` | Set reasoning depth |
| `/think <on\|off\|last>` | Control thinking visibility |
| `/status` | Show current settings |
| `/help` | Show help message |

## Architecture

```
Telegram → TelegramClient → extract_prompt() → ClaudeSDKClient.query()
                                                        ↓
                                               receive_response() stream
                                                        ↓
                                   TextBlock → StreamBridge → sendMessageDraft (live)
                                ThinkingBlock → cached (or displayed if /think on)
                                 ToolUseBlock → send_message (tool status)
                                                        ↓
                                               finalize → sendMessage (final)
                                               deliver_outbox() → files to chat
```

## Project Structure

```
claude_telegram/
├── __main__.py          Entry point
├── config.py            Environment-based configuration
├── bot.py               Polling loop and lifecycle
├── commands.py          Command dispatch
├── handler.py           Message handling orchestration
├── telegram/
│   ├── client.py        Telegram Bot API wrapper
│   ├── extract.py       Message → prompt extraction
│   ├── stream.py        Throttled draft streaming
│   └── files.py         Outbox file delivery
└── claude/
    ├── session.py       Per-user SDK session management
    └── tools.py         Tool status formatting
```

## Environment Variables

### Required

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `ALLOWED_USER_IDS` | Comma-separated authorized Telegram user IDs |

### Optional

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Claude API key (if not using subscription auth) |
| `TELEGRAM_API_BASE` | `https://api.telegram.org` | Bot API endpoint (set for local server) |
| `TELEGRAM_API_ID` | — | For local Bot API server |
| `TELEGRAM_API_HASH` | — | For local Bot API server |
| `DEFAULT_PROJECT` | `/projects` | Initial working directory |
| `DEFAULT_MODEL` | `sonnet` | Initial model (`opus`, `sonnet`, `haiku`) |
| `DEFAULT_EFFORT` | `high` | Reasoning depth (`low`, `medium`, `high`) |
| `MAX_TURNS` | `10` | Max agentic turns per query |
| `STREAM_INTERVAL_MS` | `150` | Draft update throttle in milliseconds |

### Third-Party Integrations (optional, passed through to Claude Code)

`OPENROUTER_API_KEY`, `SIMPLEFIN_ACCESS_URL`, `SPLITWISE_API_KEY`, `SPLITWISE_CONSUMER_KEY`, `SPLITWISE_CONSUMER_SECRET`, `TODOIST_API_KEY`

### Obsidian Sync (optional)

`OBSIDIAN_VAULT_NAMES`, `OBSIDIAN_AUTH_TOKEN`, `OBSIDIAN_EMAIL`, `OBSIDIAN_PASSWORD`, `OBSIDIAN_VAULT_PASSWORD`

## Testing

```bash
pip install -e ".[test]"
pytest
```

## Notes

- **Auth**: Only whitelisted user IDs can interact. Set `ALLOWED_USER_IDS`.
- **Local Bot API**: The Docker Compose setup includes a local Bot API server that lifts the 20MB/50MB file limits to 2GB. Requires `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from [my.telegram.org](https://my.telegram.org/apps).
- **Sessions**: Claude Code persists sessions on disk. Volumes preserve them across container restarts.
- **Streaming**: Uses `sendMessageDraft` (Bot API 9.5). Older Telegram clients may not render drafts mid-stream; the final `sendMessage` always works.
- **Obsidian**: Optional headless vault sync mounts notes read-only into the container.
