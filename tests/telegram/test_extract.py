"""Tests for Telegram message extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from claude_telegram.telegram.extract import _extract_file_info, extract_prompt


class TestExtractFileInfo:
    def test_document(self) -> None:
        msg = {
            "document": {
                "file_id": "abc12345xyz",
                "file_name": "report.pdf",
                "mime_type": "application/pdf",
            },
        }
        file_id, name, desc = _extract_file_info(msg)
        assert file_id == "abc12345xyz"
        assert name == "report.pdf"
        assert "application/pdf" in desc

    def test_document_no_filename(self) -> None:
        msg = {"document": {"file_id": "abc12345xyz", "mime_type": "text/plain"}}
        _, name, _ = _extract_file_info(msg)
        assert name == "document_abc12345"

    def test_photo_picks_largest(self) -> None:
        msg = {
            "photo": [
                {"file_id": "small123", "width": 100, "height": 100},
                {"file_id": "large456", "width": 1920, "height": 1080},
            ],
        }
        file_id, _, desc = _extract_file_info(msg)
        assert file_id == "large456"
        assert "1920x1080" in desc

    def test_voice(self) -> None:
        msg = {"voice": {"file_id": "voice123", "duration": 5}}
        file_id, name, desc = _extract_file_info(msg)
        assert file_id == "voice123"
        assert name.endswith(".ogg")
        assert "5s" in desc

    def test_audio_with_metadata(self) -> None:
        msg = {
            "audio": {
                "file_id": "audio123",
                "file_name": "song.mp3",
                "performer": "Artist",
                "title": "Track",
                "duration": 180,
            },
        }
        _, name, desc = _extract_file_info(msg)
        assert name == "song.mp3"
        assert "Artist - Track" in desc

    def test_video(self) -> None:
        msg = {
            "video": {
                "file_id": "video123",
                "width": 1280,
                "height": 720,
                "duration": 30,
            },
        }
        file_id, _, desc = _extract_file_info(msg)
        assert file_id == "video123"
        assert "1280x720" in desc
        assert "30s" in desc

    def test_no_file(self) -> None:
        assert _extract_file_info({"text": "hello"}) is None


class TestExtractPrompt:
    async def test_text_only(self) -> None:
        telegram = AsyncMock()
        result = await extract_prompt({"text": "hello world"}, telegram)
        assert result == "hello world"

    async def test_caption_preferred_over_empty_text(self) -> None:
        telegram = AsyncMock()
        msg = {"caption": "photo caption", "text": ""}
        result = await extract_prompt(msg, telegram)
        assert result == "photo caption"

    async def test_location(self) -> None:
        telegram = AsyncMock()
        msg = {"location": {"latitude": 40.7128, "longitude": -74.006}}
        result = await extract_prompt(msg, telegram)
        assert "40.7128" in result
        assert "-74.006" in result

    async def test_contact(self) -> None:
        telegram = AsyncMock()
        msg = {
            "contact": {
                "first_name": "John",
                "last_name": "Doe",
                "phone_number": "+1234567890",
            },
        }
        result = await extract_prompt(msg, telegram)
        assert "John Doe" in result
        assert "+1234567890" in result

    async def test_empty_message_returns_none(self) -> None:
        telegram = AsyncMock()
        result = await extract_prompt({}, telegram)
        assert result is None

    async def test_text_with_location(self) -> None:
        telegram = AsyncMock()
        msg = {
            "text": "I am here",
            "location": {"latitude": 51.5, "longitude": -0.1},
        }
        result = await extract_prompt(msg, telegram)
        assert "I am here" in result
        assert "51.5" in result
