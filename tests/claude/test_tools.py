"""Tests for tool status formatting."""

from __future__ import annotations

from claude_telegram.claude.tools import format_tool_status


class TestFormatToolStatus:
    def test_bash(self) -> None:
        result = format_tool_status("Bash", {"command": "ls -la"})
        assert "*Bash*" in result
        assert "ls -la" in result

    def test_read_simple(self) -> None:
        result = format_tool_status("Read", {"file_path": "/foo/bar.py"})
        assert "*Read*" in result
        assert "/foo/bar.py" in result

    def test_read_with_range(self) -> None:
        result = format_tool_status(
            "Read", {"file_path": "/f.py", "offset": 10, "limit": 20},
        )
        assert "10" in result
        assert "30" in result

    def test_write(self) -> None:
        result = format_tool_status("Write", {"file_path": "/out.txt"})
        assert "*Write*" in result
        assert "/out.txt" in result

    def test_edit(self) -> None:
        result = format_tool_status("Edit", {"file_path": "/src/main.py"})
        assert "*Edit*" in result

    def test_glob(self) -> None:
        result = format_tool_status("Glob", {"pattern": "**/*.py"})
        assert "*Glob*" in result
        assert "**/*.py" in result

    def test_grep_with_path(self) -> None:
        result = format_tool_status("Grep", {"pattern": "TODO", "path": "/src"})
        assert "TODO" in result
        assert "/src" in result

    def test_grep_without_path(self) -> None:
        result = format_tool_status("Grep", {"pattern": "error"})
        assert "error" in result
        assert " in " not in result

    def test_web_search(self) -> None:
        result = format_tool_status("WebSearch", {"query": "python asyncio"})
        assert "*WebSearch*" in result
        assert "python asyncio" in result

    def test_web_fetch(self) -> None:
        result = format_tool_status("WebFetch", {"url": "https://example.com"})
        assert "*WebFetch*" in result

    def test_agent(self) -> None:
        result = format_tool_status("Agent", {"description": "Search codebase"})
        assert "*Agent*" in result
        assert "Search codebase" in result

    def test_todo_write(self) -> None:
        result = format_tool_status("TodoWrite", {})
        assert "*TodoWrite*" in result

    def test_unknown_tool_with_inputs(self) -> None:
        result = format_tool_status("CustomTool", {"key": "value"})
        assert "*CustomTool*" in result

    def test_unknown_tool_empty_inputs(self) -> None:
        result = format_tool_status("CustomTool", {})
        assert "*CustomTool*" in result

    def test_truncation(self) -> None:
        long_command = "x" * 500
        result = format_tool_status("Bash", {"command": long_command})
        assert "\u2026" in result
        assert len(result) < 500
