"""Claude runtime translation tests."""

from __future__ import annotations

from unittest import TestCase

from claude_telegram.claude.events import TextDelta, ThinkingDelta, ToolStarted
from claude_telegram.claude.runtime import translate_assistant_blocks


class _TextBlock:
    def __init__(self, text: str):
        self.text = text


class _ThinkingBlock:
    def __init__(self, thinking: str):
        self.thinking = thinking


class _ToolUseBlock:
    def __init__(self, name: str, input_payload: dict[str, object]):
        self.name = name
        self.input = input_payload


class ClaudeRuntimeTranslationTests(TestCase):
    def test_translates_sdk_blocks_into_internal_events(self) -> None:
        events = translate_assistant_blocks(
            [
                _TextBlock("hello"),
                _ThinkingBlock("pondering"),
                _ToolUseBlock("Bash", {"command": "ls"}),
            ]
        )
        self.assertEqual(events[0], TextDelta(text="hello"))
        self.assertEqual(events[1], ThinkingDelta(text="pondering"))
        self.assertIsInstance(events[2], ToolStarted)
        self.assertEqual(events[2].invocation.name, "Bash")

