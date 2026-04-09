"""Internal Claude event types."""

from __future__ import annotations

from dataclasses import dataclass

from claude_telegram.domain.models import ToolInvocation


@dataclass(slots=True)
class TextDelta:
    text: str


@dataclass(slots=True)
class ThinkingDelta:
    text: str


@dataclass(slots=True)
class ToolStarted:
    invocation: ToolInvocation


@dataclass(slots=True)
class RunFinished:
    total_cost_usd: float | None = None


ClaudeRunEvent = TextDelta | ThinkingDelta | ToolStarted | RunFinished

