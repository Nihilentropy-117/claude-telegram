"""Attachment service tests."""

from __future__ import annotations

from pathlib import Path
from unittest import IsolatedAsyncioTestCase

from claude_telegram.attachments.service import AttachmentService
from claude_telegram.domain.models import ArtifactType
from tests.test_support import configured_settings


class AttachmentServiceTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._settings_context = configured_settings()
        self.settings = self._settings_context.__enter__()
        self.service = AttachmentService(self.settings)
        self.settings.outbox_dir.mkdir(parents=True, exist_ok=True)

    async def asyncTearDown(self) -> None:
        self._settings_context.__exit__(None, None, None)

    async def test_collect_new_artifacts_only_returns_new_files(self) -> None:
        old_file = self.settings.outbox_dir / "old.txt"
        old_file.write_text("old", encoding="utf-8")
        before_snapshot = await self.service.snapshot_outbox()
        new_file = self.settings.outbox_dir / "new.png"
        new_file.write_text("new", encoding="utf-8")

        artifacts = await self.service.collect_new_artifacts(before_snapshot)

        self.assertEqual([artifact.path.name for artifact in artifacts], ["new.png"])
        self.assertEqual(artifacts[0].artifact_type, ArtifactType.PHOTO)

