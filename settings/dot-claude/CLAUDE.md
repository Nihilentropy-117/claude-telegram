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
- `/temp` — Telegram file downloads land here
- `/temp/outbox/` — **drop files here to send them to the user via Telegram**

## Sending files to the user

Write any file to `/temp/outbox/` and the bot will automatically send it to the
user's Telegram chat after your response. The file is deleted once delivered.

File type routing:
- Images (`.jpg`, `.png`, `.gif`, `.webp`, `.bmp`) → `sendPhoto`
- Video (`.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`) → `sendVideo`
- Audio (`.mp3`, `.ogg`, `.wav`, `.flac`, `.m4a`, `.aac`) → `sendAudio`
- Everything else → `sendDocument`

Example: save a matplotlib chart as `/temp/outbox/chart.png` and it will appear
in chat as an image.

## Obsidian Notes

Your Obsidian vault(s) are mounted at `/user-files/notes/`.
Each vault is a subdirectory named after the vault, e.g. `/user-files/notes/My Vault/`.
Files are kept in continuous sync with Obsidian Sync via a background container.

**Permissions:**
- `/user-files/notes/<vault>/intake/` — read/write (you may create, edit, delete files here)
- All other paths under `/user-files/notes/` — read-only (do not attempt to write)

Useful patterns:
- List vaults: `ls /user-files/notes/`
- Full-text search: `rg "search term" /user-files/notes/`
- Find a note by name: `fd "note title" /user-files/notes/`
- Drop a new note into intake: write to `/user-files/notes/WanderlandReX/intake/`
