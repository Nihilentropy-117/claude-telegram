"""Format Claude tool invocations as Telegram status messages."""

from __future__ import annotations

from typing import Any


def _truncate(text: str, max_length: int) -> str:
    return text if len(text) <= max_length else text[:max_length] + "\u2026"


def format_tool_status(name: str, inputs: dict[str, Any]) -> str:
    """Render a tool invocation as a Markdown status line for Telegram."""
    match name:
        case "Bash":
            command = _truncate(inputs.get("command", ""), 400)
            return f"\u2699\ufe0f *Bash*\n```\n{command}\n```"

        case "Read":
            path = _truncate(inputs.get("file_path", ""), 200)
            offset = inputs.get("offset")
            limit = inputs.get("limit")
            if offset or limit:
                start = offset or 0
                end = start + (limit or 0)
                return f"\U0001f4d6 *Read* `{path}` (lines {start}\u2013{end})"
            return f"\U0001f4d6 *Read* `{path}`"

        case "Write":
            path = _truncate(inputs.get("file_path", ""), 200)
            return f"\u270f\ufe0f *Write* `{path}`"

        case "Edit":
            path = _truncate(inputs.get("file_path", ""), 200)
            return f"\u270f\ufe0f *Edit* `{path}`"

        case "Glob":
            pattern = _truncate(inputs.get("pattern", ""), 200)
            return f"\U0001f50d *Glob* `{pattern}`"

        case "Grep":
            pattern = _truncate(inputs.get("pattern", ""), 200)
            path = inputs.get("path", "")
            location = f" in `{_truncate(path, 100)}`" if path else ""
            return f"\U0001f50d *Grep* `{pattern}`{location}"

        case "WebSearch":
            query = _truncate(inputs.get("query", ""), 200)
            return f"\U0001f310 *WebSearch* `{query}`"

        case "WebFetch":
            url = _truncate(inputs.get("url", ""), 200)
            return f"\U0001f310 *WebFetch* `{url}`"

        case "Agent":
            description = inputs.get("description", inputs.get("prompt", ""))
            return f"\U0001f916 *Agent* _{_truncate(description, 150)}_"

        case "TodoWrite":
            return "\U0001f4dd *TodoWrite* _(updating task list)_"

        case _:
            detail = _truncate(str(inputs), 120) if inputs else ""
            if detail:
                return f"\u2699\ufe0f *{name}*: `{detail}`"
            return f"\u2699\ufe0f *{name}*"
