"""Presenter helper tests."""

from __future__ import annotations

from unittest import TestCase

from claude_telegram.telegram.presenter import TelegramPresenter


class PresenterChunkingTests(TestCase):
    def test_chunk_text_prefers_newlines(self) -> None:
        text = "line1\nline2\nline3"
        chunks = TelegramPresenter.chunk_text(text, 7)
        self.assertEqual(chunks, ["line1", "line2", "line3"])

    def test_chunk_text_falls_back_to_hard_cuts(self) -> None:
        text = "abcdefghij"
        chunks = TelegramPresenter.chunk_text(text, 4)
        self.assertEqual(chunks, ["abcd", "efgh", "ij"])

