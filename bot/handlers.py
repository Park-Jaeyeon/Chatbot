"""Telegram handlers for GG Chatbot."""
from __future__ import annotations

import logging
from textwrap import dedent

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bot.gemma_client import GEMMA_CLIENT_KEY, GemmaClient, GemmaClientError

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = dedent(
    """
    You are GG Chatbot, a friendly assistant that represents GG recommendation service.
    Keep responses concise, actionable, and polite in Korean unless the user explicitly uses another language.
    Provide clear steps or suggestions and avoid hallucinating data.
    """
).strip()


async def _send_typing(update: Update) -> None:
    if update.effective_chat:
        await update.effective_chat.send_action(ChatAction.TYPING)


def _get_client(context: ContextTypes.DEFAULT_TYPE) -> GemmaClient:
    client = context.application.bot_data.get(GEMMA_CLIENT_KEY)
    if client is None:
        raise GemmaClientError("GemmaClient 초기화가 완료되지 않았습니다.")
    return client


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "안녕하세요! GG Chatbot 입니다. 아무 메시지나 보내시면 Gemma 가 답변합니다."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "궁금한 내용을 자연어로 질문하면 Gemma 가 답변해 줍니다. /start 로 초기 안내를 볼 수 있습니다."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text:
        return
    text = message.text.strip()
    if not text:
        await message.reply_text("빈 메시지는 처리할 수 없어요. 다시 입력해주세요.")
        return

    await _send_typing(update)

    try:
        client = _get_client(context)
        gemma_response = await client.generate(
            text,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
        )
    except GemmaClientError as exc:
        logger.exception("Gemma 호출 실패")
        await message.reply_text("Gemma 응답 생성 중 오류가 발생했어요. 잠시 후 다시 시도해주세요.")
        return

    await message.reply_text(gemma_response.text)


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

