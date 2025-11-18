"""Async client wrapper for the external Gemini API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

GEMINI_CLIENT_KEY = "gemini_client"


class GeminiClientError(RuntimeError):
    """Raised when Gemini inference fails or returns invalid payload."""


@dataclass
class GeminiResponse:
    """Structured response from Gemini."""

    text: str


class GeminiClient:
    """Simple wrapper around the Gemini HTTP API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required.")

        self._api_key = api_key
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
                timeout=self._timeout,
                headers={"User-Agent": "GGChatbot-Gemini/0.1"},
            )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def generate(self, prompt: str, *, system_prompt: str | None = None) -> GeminiResponse:
        """Call Gemini's generateContent API and return the first candidate text."""

        if self._client is None:
            raise GeminiClientError("GeminiClient 가 초기화되지 않았습니다. start() 를 먼저 호출하세요.")

        # Gemini generateContent 형식에 맞춰 contents 구성
        text_blocks: list[str] = []
        if system_prompt:
            text_blocks.append(system_prompt)
        text_blocks.append(prompt)
        content_text = "\n\n".join(text_blocks)

        url = f"{self._base_url}/models/{self._model}:generateContent"
        params = {"key": self._api_key}
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": content_text},
                    ]
                }
            ]
        }

        try:
            response = await self._client.post(url, params=params, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GeminiClientError(f"Gemini API 호출 실패: {exc}") from exc

        data = response.json()
        candidates = data.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            for part in parts:
                text = str(part.get("text", "")).strip()
                if text:
                    return GeminiResponse(text=text)

        raise GeminiClientError("Gemini API 응답에 text 후보가 없습니다.")

