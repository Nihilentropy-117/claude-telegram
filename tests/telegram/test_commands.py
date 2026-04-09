"""Command helper tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from claude_telegram.domain.models import ClaudeEffort, ClaudeModel, ThinkingMode
from claude_telegram.telegram.commands import parse_effort, parse_model, parse_thinking_mode, resolve_project_path


class CommandParsingTests(TestCase):
    def test_parses_known_model_values(self) -> None:
        self.assertEqual(parse_model("opus"), ClaudeModel.OPUS)
        self.assertEqual(parse_model("bad"), None)

    def test_parses_known_effort_values(self) -> None:
        self.assertEqual(parse_effort("medium"), ClaudeEffort.MEDIUM)
        self.assertEqual(parse_effort("bad"), None)

    def test_parses_thinking_mode_values(self) -> None:
        self.assertEqual(parse_thinking_mode("on"), ThinkingMode.ON)
        self.assertEqual(parse_thinking_mode("bad"), None)

    def test_resolves_existing_project_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir)
            self.assertEqual(resolve_project_path(str(path)), str(path))
            self.assertEqual(resolve_project_path(str(path / "missing")), None)

