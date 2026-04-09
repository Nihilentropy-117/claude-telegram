"""Tests for text splitting and stream bridge logic."""

from __future__ import annotations

from claude_telegram.telegram.stream import split_text


class TestSplitText:
    def test_short_text_single_chunk(self) -> None:
        assert split_text("hello", 100) == ["hello"]

    def test_exact_limit(self) -> None:
        text = "a" * 100
        assert split_text(text, 100) == [text]

    def test_split_prefers_newline(self) -> None:
        text = "line1\nline2\nline3"
        result = split_text(text, 12)
        assert result[0] == "line1\nline2"
        assert result[1] == "line3"

    def test_split_long_no_newline(self) -> None:
        text = "a" * 200
        result = split_text(text, 100)
        assert len(result) == 2
        assert result[0] == "a" * 100
        assert result[1] == "a" * 100

    def test_empty_text(self) -> None:
        assert split_text("", 100) == [""]

    def test_newline_at_boundary(self) -> None:
        text = "a" * 50 + "\n" + "b" * 50
        result = split_text(text, 51)
        assert result[0] == "a" * 50
        assert result[1] == "b" * 50

    def test_newline_too_early_falls_back_to_hard_cut(self) -> None:
        """When the only newline is in the first quarter, use hard cut instead."""
        text = "ab\n" + "c" * 200
        result = split_text(text, 100)
        # Newline at position 2 is < 100//2=50, so hard cut at 100
        assert len(result[0]) == 100

    def test_multiple_chunks(self) -> None:
        text = "chunk1\nchunk2\nchunk3\nchunk4"
        result = split_text(text, 14)
        assert all(len(c) <= 14 for c in result)
        assert "\n".join(result) == text
