#!/bin/bash
set -euo pipefail

mkdir -p /settings/dot-claude /temp/outbox /pip-cache

rm -rf /root/.claude
ln -s /settings/dot-claude /root/.claude

if [ ! -s /settings/claude.json ]; then
    echo '{}' > /settings/claude.json
fi
rm -f /root/.claude.json
ln -s /settings/claude.json /root/.claude.json

if [ ! -x /venv/bin/python ]; then
    python -m venv /venv
    /venv/bin/pip install --upgrade pip
fi

# Recreate the mounted venv if it exists but is broken/incompatible.
if ! /venv/bin/python -c "import sys; print(sys.version_info[:2])" >/dev/null 2>&1; then
    rm -rf /venv
    python -m venv /venv
    /venv/bin/pip install --upgrade pip
fi

/venv/bin/python -m pip install --no-cache-dir --requirement /app/requirements.txt

# NOTE: Persistent bind-mounted venvs can become stale across rewrites; verify
# key runtime imports and heal by reinstalling before starting the bot.
if ! /venv/bin/python -c "import aiogram, aiosqlite, pydantic, pydantic_settings, claude_agent_sdk" >/dev/null 2>&1; then
    /venv/bin/python -m pip install --no-cache-dir --upgrade --requirement /app/requirements.txt
fi

exec "$@"
