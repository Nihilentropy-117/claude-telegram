# Claude Telegram Bot

Production-oriented Telegram bridge for Claude Code, implemented as a Python 3.12 service with persistent per-user queues, SQLite-backed preferences, live draft streaming, attachment ingestion, and automatic artifact delivery.

## What It Does

- Accepts Telegram messages from authorized users and forwards them to Claude Code.
- Preserves one Claude conversation per Telegram user until `/new`, `/project`, `/model`, or `/effort` resets it.
- Streams partial assistant output with `sendMessageDraft`, then sends the final response as normal Telegram messages.
- Accepts documents, photos, voice notes, audio files, videos, locations, and contacts.
- Saves inbound files under `/temp` and tells Claude where they were written.
- Sends files that Claude writes to `/temp/outbox/` back to Telegram automatically.
- Runs with Docker Compose alongside a local Telegram Bot API server and an optional Obsidian sync sidecar.

## Commands

- `/start`
- `/help`
- `/new`
- `/interrupt`
- `/project <path>`
- `/model <opus|sonnet|haiku>`
- `/effort <low|medium|high>`
- `/think <on|off|last>`
- `/status`

## Install

1. Copy `.env.example` to `.env`.
2. Fill in the required values.
3. Adjust the bind mounts in `docker-compose.yml` if your local project and file paths differ.
4. For local development outside Docker:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```bash
docker compose up -d --build
```

The stack starts:

- `claude-bot`: the Python application
- `telegram-bot-api`: local Telegram Bot API server for large-file support and direct shared-volume file reads
- `obsidian-sync`: optional continuous Obsidian Sync mirror

## Test

Create a local virtual environment, install the pinned dependencies, and run:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Environment Variables

Required:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`

Optional:

- `ALLOWED_USER_IDS`
- `TELEGRAM_API_BASE`
- `DEFAULT_PROJECT`
- `DEFAULT_MODEL`
- `DEFAULT_EFFORT`
- `MAX_TURNS`
- `STREAM_INTERVAL_MS`
- `CLAUDE_PERMISSION_MODE`
- `STATE_DB_PATH`
- `TEMP_DIR`
- `OUTBOX_DIR`
- `LOCAL_BOT_API_STORAGE_PATH`
- `POLL_TIMEOUT_SECONDS`
- `LOG_LEVEL`
- `ANTHROPIC_API_KEY`
- `OPENROUTER_API_KEY`
- `SIMPLEFIN_ACCESS_URL`
- `SPLITWISE_API_KEY`
- `SPLITWISE_CONSUMER_KEY`
- `SPLITWISE_CONSUMER_SECRET`
- `TODOIST_API_KEY`
- `OBSIDIAN_VAULT_NAMES`
- `OBSIDIAN_AUTH_TOKEN`
- `OBSIDIAN_EMAIL`
- `OBSIDIAN_PASSWORD`
- `OBSIDIAN_VAULT_PASSWORD`

## Mounted Paths Claude Relies On

- `/projects`: default working tree root for Claude
- `/temp`: inbound file staging area
- `/temp/outbox`: outbound artifact directory
- `/settings`: persisted Claude config and SQLite state
- `/user-files/files`: read-only user files
- `/user-files/media`: read-only media
- `/user-files/rw_files`: writable shared files
- `/user-files/rw_media`: writable shared media
- `/user-files/notes`: Obsidian vault mirror

## Dependency Pins

- `aiogram==3.26.0`
- `claude-agent-sdk==0.1.48`
- `pydantic==2.12.5`
- `pydantic-settings==2.12.0`
- `aiosqlite==0.22.1`
- `obsidian-headless@0.0.8`
