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
    gemma_base_url: str = "http://localhost:11434"
    gemma_model: str = "gemma:2b"
    request_timeout: float = 30.0

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
        return cls(
            telegram_bot_token=token,
            gemma_base_url=base_url,
            gemma_model=model,
            request_timeout=timeout,
        )


settings = Settings.load()

