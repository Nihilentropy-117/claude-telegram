"""Tests for outbox file delivery."""

from __future__ import annotations

from claude_telegram.telegram.files import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
)


class TestExtensionSets:
    def test_no_overlap_between_categories(self) -> None:
        assert not (IMAGE_EXTENSIONS & VIDEO_EXTENSIONS)
        assert not (IMAGE_EXTENSIONS & AUDIO_EXTENSIONS)
        assert not (VIDEO_EXTENSIONS & AUDIO_EXTENSIONS)

    def test_common_image_extensions(self) -> None:
        for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            assert ext in IMAGE_EXTENSIONS

    def test_common_video_extensions(self) -> None:
        for ext in (".mp4", ".mov", ".webm"):
            assert ext in VIDEO_EXTENSIONS

    def test_common_audio_extensions(self) -> None:
        for ext in (".mp3", ".ogg", ".wav", ".flac"):
            assert ext in AUDIO_EXTENSIONS
