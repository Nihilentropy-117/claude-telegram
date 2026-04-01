# Claude Code Telegram Bot

Stream Claude Code responses to Telegram in real-time via `sendMessageDraft` (Bot API 9.5).

No frameworks. Raw `httpx` against Telegram API, `asyncio.subprocess` for Claude Code CLI.

## Setup

1. **Create a bot** via [@BotFather](https://t.me/BotFather) on Telegram. Enable streaming in BotFather settings.

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

5. **Mount your projects** by editing `docker-compose.yml` volumes. The default maps `~/projects` to `/projects` inside the container.

## Commands

| Command | Description |
|---|---|
| `/new [name]` | Start a new Claude Code session |
| `/continue` | Resume the last session |
| `/resume <id>` | Resume a specific session |
| `/compact` | Compress session context |
| `/project <path>` | Switch working directory (container paths) |
| `/model <opus\|sonnet\|haiku>` | Switch model |
| `/effort <low\|medium\|high>` | Set reasoning depth |
| `/tools <safe\|full>` | Toggle tool permissions |
| `/think <on\|off\|last>` | Control thinking visibility |
| `/status` | Show current config |

## How it works

```
You (Telegram) → bot.py → claude -p --output-format stream-json
                                    ↓
                              NDJSON events
                                    ↓
                         text_delta → sendMessageDraft (live streaming)
                      thinking_delta → cached (or streamed if /think on)
                                    ↓
                         message_stop → sendMessage (final)
```

## Notes

- **Auth**: Only whitelisted Telegram user IDs can interact. Set `ALLOWED_USER_IDS` in `.env`.
- **Skills**: Any skills in `~/.claude/skills/` or your project's `.claude/skills/` are picked up automatically by Claude Code. No bot-side config needed.
- **Sessions**: Claude Code persists sessions on disk. The `claude-data` volume preserves them across container restarts.
- **Tools**: Default is read-only (`Read,Grep,Glob`). Use `/tools full` to enable writes — this gives Claude Code `Read,Write,Edit,Bash,Grep,Glob`.
- **Streaming commission**: Telegram charges 15% on Stars purchases when streaming is enabled. Irrelevant unless you add paid features.
- **sendMessageDraft**: If the Telegram client doesn't support it yet (older versions), the draft just won't render mid-stream. The final `sendMessage` always works.
