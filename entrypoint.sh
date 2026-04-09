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

/venv/bin/pip install --no-cache-dir --requirement /app/requirements.txt

exec "$@"
