"""Async client for external media search (GIFs/images)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

MEDIA_CLIENT_KEY = "media_client"


class MediaClientError(RuntimeError):
    """Raised when media search fails."""


@dataclass
class MediaResult:
    """Structured result for a single media item."""

    url: str


class TenorClient:
    """Very small wrapper around the Tenor GIF search API.

    참고: 이 클라이언트는 단일 GIF URL 만 반환하며,
    텔레그램의 send_animation 에 바로 사용할 수 있습니다.
    """

    def __init__(
        self,
        *,
        api_key: str,
        timeout: float = 5.0,
        limit: int = 1,
    ) -> None:
        if not api_key:
            raise ValueError("Tenor API key is required.")
        self._api_key = api_key
        self._timeout = timeout
        self._limit = limit
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": "GGChatbot-Media/0.1"},
            )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search_gif(self, query: str) -> Optional[MediaResult]:
        """Search a GIF for the query and return the first result, if any."""

        if self._client is None:
            raise MediaClientError("TenorClient 가 초기화되지 않았습니다. start() 를 먼저 호출하세요.")

        params = {
            "q": query,
            "key": self._api_key,
            "client_key": "gg-chatbot",
            "limit": str(self._limit),
        }
        url = "https://tenor.googleapis.com/v2/search"

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MediaClientError(f"Tenor API 호출 실패: {exc}") from exc

        data = response.json()
        results = data.get("results") or []
        if not results:
            return None

        # Tenor v2 응답에서 적절한 GIF URL 선택
        media_formats = results[0].get("media_formats") or {}
        # 우선순위: gif > mediumgif > tinygif
        for key in ("gif", "mediumgif", "tinygif"):
            fmt = media_formats.get(key)
            if fmt and isinstance(fmt, dict):
                url = str(fmt.get("url", "")).strip()
                if url:
                    return MediaResult(url=url)

        return None

