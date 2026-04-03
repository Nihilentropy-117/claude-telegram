#!/bin/bash
set -e

# --- Claude Code config ---
mkdir -p /settings/dot-claude

# Symlink ~/.claude → /settings/dot-claude
rm -rf /root/.claude
ln -sf /settings/dot-claude /root/.claude

# Symlink ~/.claude.json → /settings/claude.json
[ -s /settings/claude.json ] || echo '{}' > /settings/claude.json
rm -f /root/.claude.json
ln -sf /settings/claude.json /root/.claude.json

# --- Persistent venv ---
if [ ! -f /venv/bin/python ]; then
    python -m venv /venv
    /venv/bin/pip install --upgrade pip
fi
# Ensure bot dependencies are in the venv
/venv/bin/pip install --quiet -r /app/requirements.txt


exec "$@"
