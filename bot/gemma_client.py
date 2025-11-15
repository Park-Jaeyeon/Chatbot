"""Async client wrapper for the local Gemma (Ollama) API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

GEMMA_CLIENT_KEY = "gemma_client"


class GemmaClientError(RuntimeError):
    """Raised when Gemma inference fails or returns invalid payload."""


@dataclass
class GemmaResponse:
    """Structured response from Gemma."""

    text: str


class GemmaClient:
    """Simple wrapper around the Ollama local HTTP API."""

    def __init__(self, *, base_url: str, model: str, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def model(self) -> str:
        return self._model

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={"User-Agent": "GGChatbot/0.1"},
            )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def generate(self, prompt: str, *, system_prompt: str | None = None) -> GemmaResponse:
        if self._client is None:
            raise GemmaClientError("GemmaClient 가 초기화되지 않았습니다. start() 를 먼저 호출하세요.")

        payload: dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = await self._client.post("/api/generate", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GemmaClientError(f"Gemma API 호출 실패: {exc}") from exc

        data = response.json()
        text = str(data.get("response", "")).strip()
        if not text:
            raise GemmaClientError("Gemma API 응답에 response 필드가 없거나 비어 있습니다.")

        return GemmaResponse(text=text)

