"""Entry point for the GG Chatbot Telegram bot."""
from __future__ import annotations

import asyncio
import logging

from telegram.ext import AIORateLimiter, Application, ApplicationBuilder

from config import MissingSettingError, Settings, settings
from bot.gemma_client import GEMMA_CLIENT_KEY, GemmaClient
from bot.handlers import register_handlers
from bot.logger import configure_logging

logger = logging.getLogger(__name__)


def build_application(app_settings: Settings) -> Application:
    """Create and configure the Telegram application instance."""

    gemma_client = GemmaClient(
        base_url=app_settings.gemma_base_url,
        model=app_settings.gemma_model,
        timeout=app_settings.request_timeout,
    )

    async def _post_init(application: Application) -> None:
        await gemma_client.start()
        application.bot_data[GEMMA_CLIENT_KEY] = gemma_client
        logger.info(
            "Gemma client 초기화 완료 | model=%s | base_url=%s",
            gemma_client.model,
            app_settings.gemma_base_url,
        )

    async def _post_shutdown(application: Application) -> None:
        await gemma_client.aclose()
        application.bot_data.pop(GEMMA_CLIENT_KEY, None)
        logger.info("Gemma client 연결을 정상적으로 종료했습니다.")

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


async def run() -> None:
    """Configure logging, build handlers, and start polling."""

    configure_logging()
    app = build_application(settings)

    logger.info(
        "Starting GG Chatbot | model=%s | base_url=%s",
        settings.gemma_model,
        settings.gemma_base_url,
    )
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main() -> None:
    """CLI entrypoint for running the bot with asyncio."""

    try:
        asyncio.run(run())
    except MissingSettingError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
