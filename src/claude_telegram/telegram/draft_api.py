"""Raw Bot API helper for sendMessageDraft."""

from __future__ import annotations

import asyncio
import json
from urllib import request


class DraftMessageApi:
    """Small JSON client for Bot API methods missing from aiogram."""

    def __init__(self, api_base: str, bot_token: str):
        self._url = f"{api_base.rstrip('/')}/bot{bot_token}/sendMessageDraft"

    async def send_draft(self, chat_id: int, draft_id: int, text: str) -> None:
        # NOTE: sendMessageDraft is available on the Bot API but not exposed as a
        # stable aiogram method, so this adapter uses direct JSON POSTs just for drafts.
        payload = json.dumps(
            {
                "chat_id": chat_id,
                "random_id": draft_id,
                "text": text,
            }
        ).encode("utf-8")
        await asyncio.to_thread(self._send_sync, payload)

    def _send_sync(self, payload: bytes) -> None:
        raw_request = request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(raw_request, timeout=30) as response:
            if response.status >= 400:
                raise RuntimeError(f"sendMessageDraft failed with HTTP {response.status}.")

