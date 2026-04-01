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

# --- Global CLAUDE.md ---
cat > /settings/dot-claude/CLAUDE.md << 'CLAUDEMD'
# Environment

You are running inside a sandboxed Docker container with full root access.
You have unrestricted permissions — never ask for confirmation to run commands.

## Installing packages

- **Python**: Always use the venv at `/venv`. It persists across restarts.
  - `pip install <package>` (venv is already activated, pip cache is persistent)
  - `uv pip install <package>` (also uses the venv)
- **System packages**: `apt-get update && apt-get install -y <package>` (no sudo needed)
  - Apt cache is persistent, so repeated installs are fast
  - Apt packages survive container restarts but not image rebuilds
- **Node packages**: `npm install -g <package>`

## Pre-installed tools

ffmpeg, imagemagick, pandoc, poppler-utils (pdftotext/pdfimages), ghostscript,
sox, exiftool, git, curl, wget, jq, ripgrep, fd-find, tree, htop, cmake,
pkg-config, sqlite3, Node.js 22, Python 3.12, uv.

Dev libraries installed: libffi, libssl, libxml2, libxslt (most pip packages compile cleanly).

## Working directories

- `/projects` — mounted project directories from the host
- `/venv` — persistent Python virtual environment
CLAUDEMD

exec "$@"
