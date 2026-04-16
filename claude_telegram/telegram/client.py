"""Async HTTP wrapper for the Telegram Bot API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096

# Local Bot API server stores downloaded files at this path inside the container.
LOCAL_BOT_API_DATA = Path("/var/lib/telegram-bot-api")


class TelegramClient:
    """Low-level async wrapper for Telegram Bot API methods.

    Supports both the cloud API and a self-hosted local Bot API server.
    With a local server, file downloads read directly from the shared
    filesystem volume instead of making HTTP requests.
    """

    def __init__(
        self, token: str, http: httpx.AsyncClient, api_base: str,
    ) -> None:
        base = api_base.rstrip("/")
        self._api = f"{base}/bot{token}"
        self._file_api = f"{base}/file/bot{token}"
        self._http = http

    async def _call(
        self, method: str, *, http_timeout: int = 60, **params: Any,
    ) -> dict[str, Any]:
        filtered = {k: v for k, v in params.items() if v is not None}
        response = await self._http.post(
            f"{self._api}/{method}", json=filtered, timeout=http_timeout,
        )
        data: dict[str, Any] = response.json()
        if not data.get("ok"):
            log.error("Telegram %s failed: %s", method, data)
        return data

    # -- Bot info -----------------------------------------------------------

    async def get_me(self) -> dict[str, Any]:
        return await self._call("getMe")

    # -- Updates ------------------------------------------------------------

    async def get_updates(
        self, offset: int | None = None, timeout: int = 30,
    ) -> list[dict[str, Any]]:
        data = await self._call(
            "getUpdates",
            http_timeout=timeout + 10,
            offset=offset,
            timeout=timeout,
        )
        return data.get("result", [])

    # -- Messages -----------------------------------------------------------

    async def send_message(
        self, chat_id: int, text: str, parse_mode: str = "Markdown",
    ) -> dict[str, Any]:
        return await self._call(
            "sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode,
        )

    async def send_draft(
        self, chat_id: int, draft_id: int, text: str,
    ) -> dict[str, Any]:
        """Push a streaming draft update (Telegram Bot API 9.5)."""
        return await self._call(
            "sendMessageDraft", chat_id=chat_id, random_id=draft_id, text=text,
        )

    async def send_chat_action(
        self, chat_id: int, action: str = "typing",
    ) -> dict[str, Any]:
        return await self._call(
            "sendChatAction", chat_id=chat_id, action=action,
        )

    # -- Files: download ----------------------------------------------------

    async def get_file(self, file_id: str) -> dict[str, Any]:
        return await self._call("getFile", file_id=file_id)

    async def download_file(self, file_path: str) -> bytes:
        """Download file content. Reads from local filesystem when available."""
        local = (
            Path(file_path)
            if file_path.startswith("/")
            else LOCAL_BOT_API_DATA / file_path
        )
        if local.exists():
            return local.read_bytes()
        response = await self._http.get(
            f"{self._file_api}/{file_path}", timeout=120,
        )
        response.raise_for_status()
        return response.content

    # -- Files: upload ------------------------------------------------------

    async def _upload(
        self,
        method: str,
        field: str,
        chat_id: int,
        file_path: str,
        caption: str | None = None,
    ) -> dict[str, Any]:
        path = Path(file_path)
        form_data: dict[str, str] = {"chat_id": str(chat_id)}
        if caption:
            form_data["caption"] = caption
        files = {field: (path.name, path.read_bytes())}
        response = await self._http.post(
            f"{self._api}/{method}", data=form_data, files=files, timeout=120,
        )
        return response.json()

    async def send_document(
        self, chat_id: int, path: str, caption: str | None = None,
    ) -> dict[str, Any]:
        return await self._upload("sendDocument", "document", chat_id, path, caption)

    async def send_photo(
        self, chat_id: int, path: str, caption: str | None = None,
    ) -> dict[str, Any]:
        return await self._upload("sendPhoto", "photo", chat_id, path, caption)

    async def send_video(
        self, chat_id: int, path: str, caption: str | None = None,
    ) -> dict[str, Any]:
        return await self._upload("sendVideo", "video", chat_id, path, caption)

    async def send_audio(
        self, chat_id: int, path: str, caption: str | None = None,
    ) -> dict[str, Any]:
        return await self._upload("sendAudio", "audio", chat_id, path, caption)
