"""Entry point for the GG Chatbot Telegram bot."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from telegram.ext import AIORateLimiter, Application, ApplicationBuilder

# Ensure project root is on sys.path when running as a script (python bot/bot.py)
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import MissingSettingError, Settings, settings
from bot.gemma_client import GEMMA_CLIENT_KEY, GemmaClient
from bot.gemini_client import GEMINI_CLIENT_KEY, GeminiClient
from bot.logger import configure_logging
from bot.memory import JsonFileMemoryStore
from bot.media_client import MEDIA_CLIENT_KEY, TenorClient
from bot.stickers import STICKER_STORE_KEY, StickerStore
from bot.learning import LEARNING_STORE_KEY, LearningStore
from bot.handlers import register_handlers

logger = logging.getLogger(__name__)


def build_application(app_settings: Settings) -> Application:
    """Create and configure the Telegram application instance."""

    gemma_client = GemmaClient(
        base_url=app_settings.gemma_base_url,
        model=app_settings.gemma_model,
        timeout=app_settings.request_timeout,
    )

    gemini_client: GeminiClient | None = None
    if app_settings.gemini_api_key:
        gemini_client = GeminiClient(
            api_key=app_settings.gemini_api_key,
            base_url=app_settings.gemini_base_url,
            model=app_settings.gemini_model,
            timeout=app_settings.request_timeout,
        )

    # Very lightweight JSON-based memory store so the bot can
    # remember recent conversations per chat across restarts.
    memory_store = JsonFileMemoryStore(
        ROOT_DIR / "data" / "user_memory.json",
        max_messages=120,  # 안전빵으로 60턴 정도까지 유지
    )

    # Simple JSON store for reaction stickers per category.
    sticker_store = StickerStore(ROOT_DIR / "data" / "stickers.json")

    # Simple per-chat learning store for question -> answer overrides.
    learning_store = LearningStore(ROOT_DIR / "data" / "learning.json")

    media_client: TenorClient | None = None
    if app_settings.tenor_api_key:
        media_client = TenorClient(
            api_key=app_settings.tenor_api_key,
            timeout=min(app_settings.request_timeout, 10.0),
        )

    async def _post_init(application: Application) -> None:
        await gemma_client.start()
        application.bot_data[GEMMA_CLIENT_KEY] = gemma_client

        if gemini_client is not None:
            await gemini_client.start()
            application.bot_data[GEMINI_CLIENT_KEY] = gemini_client

        if media_client is not None:
            await media_client.start()
            application.bot_data[MEDIA_CLIENT_KEY] = media_client

        application.bot_data["memory_store"] = memory_store
        application.bot_data[STICKER_STORE_KEY] = sticker_store
        application.bot_data[LEARNING_STORE_KEY] = learning_store
        logger.info(
            "Gemma client 초기화 완료 | model=%s | base_url=%s",
            gemma_client.model,
            app_settings.gemma_base_url,
        )

    async def _post_shutdown(application: Application) -> None:
        await gemma_client.aclose()
        if gemini_client is not None:
            await gemini_client.aclose()
        if media_client is not None:
            await media_client.aclose()
        application.bot_data.pop(GEMMA_CLIENT_KEY, None)
        application.bot_data.pop(GEMINI_CLIENT_KEY, None)
        application.bot_data.pop(MEDIA_CLIENT_KEY, None)
        application.bot_data.pop("memory_store", None)
        application.bot_data.pop(STICKER_STORE_KEY, None)
        application.bot_data.pop(LEARNING_STORE_KEY, None)
        logger.info("Gemma/Gemini/Media/Sticker client 연결을 정상적으로 종료했습니다.")

    application = (
        ApplicationBuilder()
        .token(app_settings.telegram_bot_token)
        .rate_limiter(AIORateLimiter())
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    register_handlers(application)
    return application


def run() -> None:
    """Configure logging, build handlers, and start polling (blocking)."""

    # Explicitly create/set event loop for compatibility on Windows & Py3.11+
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    configure_logging()
    app = build_application(settings)

    logger.info(
        "Starting GG Chatbot | model=%s | base_url=%s",
        settings.gemma_model,
        settings.gemma_base_url,
    )
    app.run_polling(drop_pending_updates=True)


def main() -> None:
    """CLI entrypoint for running the bot."""

    try:
        run()
    except MissingSettingError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
