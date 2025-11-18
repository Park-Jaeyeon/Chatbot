"""Application configuration helpers and Settings dataclass."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class MissingSettingError(RuntimeError):
    """Raised when a required environment variable is absent."""


@dataclass(slots=True)
class Settings:
    """Container for application configuration values."""

    telegram_bot_token: str
    # Local Gemma (Ollama)
    gemma_base_url: str = "http://localhost:11434"
    gemma_model: str = "gemma:2b"
    request_timeout: float = 30.0

    # Optional external Gemini API (for fallback / learning)
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-1.5-flash"

    # Optional Tenor API (for GIF search)
    tenor_api_key: str | None = None

    @classmethod
    def load(cls, *, env: Optional[dict[str, str]] = None) -> "Settings":
        """Load settings from environment variables."""

        source = env or os.environ
        token = source.get("TELEGRAM_BOT_TOKEN")
        if not token:
            raise MissingSettingError(
                "환경변수 TELEGRAM_BOT_TOKEN 이 설정되어야 텔레그램 봇을 실행할 수 있습니다."
            )

        base_url = source.get("GEMMA_BASE_URL", "http://localhost:11434")
        model = source.get("GEMMA_MODEL", "gemma:2b")
        timeout = float(source.get("REQUEST_TIMEOUT", "30"))

        gemini_api_key = source.get("GEMINI_API_KEY")
        gemini_base_url = source.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
        gemini_model = source.get("GEMINI_MODEL", "gemini-1.5-flash")

        tenor_api_key = source.get("TENOR_API_KEY")

        return cls(
            telegram_bot_token=token,
            gemma_base_url=base_url,
            gemma_model=model,
            request_timeout=timeout,
            gemini_api_key=gemini_api_key,
            gemini_base_url=gemini_base_url,
            gemini_model=gemini_model,
            tenor_api_key=tenor_api_key,
        )


settings = Settings.load()

