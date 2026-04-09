"""Pure helpers for command validation."""

from __future__ import annotations

from pathlib import Path

from claude_telegram.domain.models import ClaudeEffort, ClaudeModel, ThinkingMode


def parse_model(value: str) -> ClaudeModel | None:
    try:
        return ClaudeModel(value.strip().lower())
    except ValueError:
        return None


def parse_effort(value: str) -> ClaudeEffort | None:
    try:
        return ClaudeEffort(value.strip().lower())
    except ValueError:
        return None


def parse_thinking_mode(value: str) -> ThinkingMode | None:
    try:
        return ThinkingMode(value.strip().lower())
    except ValueError:
        return None


def resolve_project_path(value: str) -> str | None:
    path = value.strip()
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_dir():
        return None
    return str(candidate)

