"""Telegram handlers for GG Chatbot."""
from __future__ import annotations

import logging
import random
from textwrap import dedent

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bot.gemma_client import GEMMA_CLIENT_KEY, GemmaClient, GemmaClientError
from bot.gemini_client import GEMINI_CLIENT_KEY, GeminiClient, GeminiClientError
from bot.media_client import MEDIA_CLIENT_KEY, TenorClient, MediaClientError
from bot.memory import MemoryStore
from bot.stickers import STICKER_STORE_KEY, StickerStore

logger = logging.getLogger(__name__)

HISTORY_KEY = "conversation_history"
# 너무 많은 히스토리를 보내면 응답이 느려지므로 최근 3턴만 유지
MAX_HISTORY_TURNS = 3
# 채팅별 미디어(스티커/GIF) 기능 토글 키
MEDIA_ENABLED_KEY = "media_enabled"
# 미디어 반응 확률 (과도한 스팸을 막기 위해 조절)
MEDIA_PROB_GROUP = 0.35
MEDIA_PROB_PRIVATE = 0.6
# 스티커 사용 시 허용 사용자 id 리스트 (없으면 전체)
STICKER_ALLOWED_USERS_KEY = "sticker_allowed_users"

DEFAULT_SYSTEM_PROMPT = dedent(
    """
    당신은 GG 추천 서비스를 대표하는 챗봇입니다.

    - 항상 한국어로 정중한 존댓말로 대화합니다.
    - 영어를 괄호 안에 넣어 예: 안녕하세요(Hello) 와 같이 표기하지 않습니다.
    - 사용자가 영어로 말하더라도, 답변은 한국어로 자연스럽게 번역하여 설명합니다.
    - 답변은 2~3문단 또는 bullet 3~5개 내에서 끝내고, 불필요하게 길지 않게 유지합니다.
    - 대화 히스토리가 함께 주어지면 이를 잘 참고하여 일관된 맥락을 유지합니다.
    - 사실이 불확실한 내용은 단정적으로 말하지 말고, 추측임을 분명히 밝힙니다.
    - 만약 질문이 당신의 지식 범위를 벗어나거나 확실한 답을 할 수 없다고 판단되면,
      아무 설명도 하지 말고 정확히 'UNSURE' 라는 한 단어만 출력합니다.
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


def _get_memory_store(context: ContextTypes.DEFAULT_TYPE) -> MemoryStore | None:
    store = context.application.bot_data.get("memory_store")
    if isinstance(store, MemoryStore):
        return store
    return None


def _get_media_enabled(context: ContextTypes.DEFAULT_TYPE) -> bool:
    # 기본은 켜짐
    return context.chat_data.get(MEDIA_ENABLED_KEY, True)


def _set_media_enabled(context: ContextTypes.DEFAULT_TYPE, enabled: bool) -> None:
    context.chat_data[MEDIA_ENABLED_KEY] = enabled


def _get_allowed_users(context: ContextTypes.DEFAULT_TYPE) -> list[int] | None:
    users = context.chat_data.get(STICKER_ALLOWED_USERS_KEY)
    if isinstance(users, list):
        try:
            return [int(u) for u in users]
        except Exception:  # pragma: no cover
            return None
    return None


def _set_allowed_users(context: ContextTypes.DEFAULT_TYPE, users: list[int] | None) -> None:
    if users is None:
        context.chat_data.pop(STICKER_ALLOWED_USERS_KEY, None)
    else:
        context.chat_data[STICKER_ALLOWED_USERS_KEY] = list(users)


def _get_gemini_client(context: ContextTypes.DEFAULT_TYPE) -> GeminiClient | None:
    client = context.application.bot_data.get(GEMINI_CLIENT_KEY)
    if isinstance(client, GeminiClient):
        return client
    return None


def _get_media_client(context: ContextTypes.DEFAULT_TYPE) -> TenorClient | None:
    client = context.application.bot_data.get(MEDIA_CLIENT_KEY)
    if isinstance(client, TenorClient):
        return client
    return None


def _get_sticker_store(context: ContextTypes.DEFAULT_TYPE) -> StickerStore | None:
    store = context.application.bot_data.get(STICKER_STORE_KEY)
    if isinstance(store, StickerStore):
        return store
    return None


def _infer_reaction_query(text: str) -> str | None:
    """간단한 규칙 기반으로 상황에 맞는 GIF 검색어를 추론합니다."""

    t = text.lower()
    # 웃음 / 재미
    if any(k in t for k in ("ㅋㅋ", "ㅎㅎ", "lol", "웃기", "재밌", "웃겨")):
        return "funny korean meme"
    # 축하 / 좋은 일
    if any(k in t for k in ("축하", "congrats", "합격", "승진", "생일", "birthday")):
        return "congratulations party"
    # 인사
    if any(k in t for k in ("안녕", "안녕하세요", "hi", "hello")):
        return "anime waving hello"
    # 위로 / 힘들 때
    if any(k in t for k in ("힘들", "슬퍼", "우울", "위로", "ㅠㅠ", "ㅜㅜ", "sad")):
        return "comforting hug"
    # 화남 / 짜증
    if any(k in t for k in ("화나", "짜증", "빡쳐", "angry", "열받")):
        return "angry reaction meme"
    # 고마움
    if any(k in t for k in ("고마워", "감사", "thank", "thx")):
        return "thank you cute"
    return None


def _infer_reaction_category(text: str) -> str | None:
    """텍스트로부터 간단한 리액션 카테고리(funny, congrats 등)를 추론합니다."""

    t = text.lower()
    if any(k in t for k in ("ㅋㅋ", "ㅎㅎ", "lol", "웃기", "재밌", "웃겨")):
        return "funny"
    if any(k in t for k in ("축하", "congrats", "합격", "승진", "생일", "birthday")):
        return "congrats"
    if any(k in t for k in ("안녕", "안녕하세요", "hi", "hello")):
        return "greeting"
    if any(k in t for k in ("힘들", "슬퍼", "우울", "위로", "ㅠㅠ", "ㅜㅜ", "sad")):
        return "comfort"
    if any(k in t for k in ("화나", "짜증", "빡쳐", "angry", "열받")):
        return "angry"
    if any(k in t for k in ("고마워", "감사", "thank", "thx")):
        return "thanks"
    return None


def _get_history(context: ContextTypes.DEFAULT_TYPE, chat_id: int | None) -> list[dict[str, str]]:
    """Load recent conversation history from in-memory chat_data and persistent store.

    chat_data 는 러닝 중 캐시, memory_store 는 재시작 이후까지 유지되는 히스토리입니다.
    둘을 합쳐서 최근 MAX_HISTORY_TURNS 쌍만 사용합니다.
    """
    history: list[dict[str, str]] = context.chat_data.get(HISTORY_KEY, [])

    store = _get_memory_store(context)
    if store is not None and chat_id is not None:
        try:
            persisted = store.load(chat_id)
            if persisted:
                history = persisted
        except Exception:  # pragma: no cover - defensive
            logger.exception("메모리 저장소에서 히스토리 로드 실패")

    # 안전장치: 구조가 엉켜 있어도 최소한 리스트 형태로만 유지
    normalized: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip() or "user"
        text = str(item.get("text", "")).strip()
        if text:
            normalized.append({"role": role, "text": text})

    max_messages = MAX_HISTORY_TURNS * 2
    if len(normalized) > max_messages:
        normalized = normalized[-max_messages:]

    context.chat_data[HISTORY_KEY] = list(normalized)
    return normalized


def _update_history(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int | None,
    user_text: str,
    bot_text: str,
) -> None:
    history: list[dict[str, str]] = context.chat_data.get(HISTORY_KEY, [])
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": bot_text})

    max_messages = MAX_HISTORY_TURNS * 2
    if len(history) > max_messages:
        history[:] = history[-max_messages:]

    context.chat_data[HISTORY_KEY] = history

    store = _get_memory_store(context)
    if store is not None and chat_id is not None:
        try:
            store.save(chat_id, history)
        except Exception:  # pragma: no cover - defensive
            logger.exception("메모리 저장소에 히스토리 저장 실패")


def _build_prompt_with_history(history: list[dict[str, str]], user_text: str) -> str:
    if not history:
        return f"사용자: {user_text}\n챗봇:"

    lines: list[str] = []
    lines.append("아래는 사용자와 챗봇 사이의 이전 대화입니다.")
    for turn in history:
        role = "사용자" if turn.get("role") == "user" else "챗봇"
        text = turn.get("text", "").strip()
        if text:
            lines.append(f"{role}: {text}")

    lines.append("")
    lines.append("위의 대화를 자연스럽게 이어서 다음 사용자의 발화에 답변해 주세요.")
    lines.append(f"사용자: {user_text}")
    lines.append("챗봇:")
    return "\n".join(lines)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "안녕하세요! GG Chatbot 입니다. 아무 메시지나 보내시면 Gemma 가 답변합니다."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "궁금한 내용을 자연어로 질문하면 Gemma 가 답변해 줍니다. /start 로 초기 안내를 볼 수 있습니다."
    )


async def clear_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else None
    store = _get_memory_store(context)
    if chat_id is not None and store is not None:
        store.clear(chat_id)
    context.chat_data.pop(HISTORY_KEY, None)
    await update.message.reply_text("이 채팅의 대화 히스토리를 모두 삭제했어요.")


async def list_stickers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = _get_sticker_store(context)
    if store is None:
        await update.message.reply_text("스티커 저장소가 초기화되지 않았습니다.")
        return
    counts = store.list_counts_with_owners()
    if not counts:
        await update.message.reply_text("아직 저장된 스티커가 없습니다.")
        return
    lines: list[str] = []
    for cat, info in sorted(counts.items()):
        cnt = info.get("count", 0)
        owners = info.get("owners", {})
        owner_str = ", ".join(f"{uid}({c})" for uid, c in sorted(owners.items(), key=lambda x: -x[1]))
        lines.append(f"- {cat}: {cnt}개" + (f" | owners: {owner_str}" if owner_str else ""))
    await update.message.reply_text("저장된 스티커 목록:\n" + "\n".join(lines))


async def clear_stickers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = _get_sticker_store(context)
    if store is None:
        await update.message.reply_text("스티커 저장소가 초기화되지 않았습니다.")
        return

    # 명시된 카테고리만 삭제. 지정 없으면 misc 를 기본값으로
    args = context.args if context.args else []
    category = args[0] if args else "misc"
    store.clear_category(category)
    await update.message.reply_text(f"'{category}' 카테고리의 스티커를 삭제했습니다.")


async def set_sticker_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """스티커 사용을 특정 user_id 목록으로 제한하거나 전체 허용."""

    if not context.args:
        _set_allowed_users(context, None)
        await update.message.reply_text("스티커 사용 대상을 전체로 초기화했습니다.")
        return

    try:
        users = [int(arg) for arg in context.args if arg.strip()]
    except ValueError:
        await update.message.reply_text("user_id 는 숫자로 입력해주세요. 예: /use_stickers 12345 67890")
        return

    _set_allowed_users(context, users)
    await update.message.reply_text(f"스티커 사용을 다음 user_id 로 제한했습니다: {', '.join(map(str, users))}")


async def enable_media_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_media_enabled(context, True)
    await update.message.reply_text("이 채팅에서 움짤/스티커 자동 반응을 켰습니다.")


async def disable_media_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_media_enabled(context, False)
    await update.message.reply_text("이 채팅에서 움짤/스티커 자동 반응을 껐습니다.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text:
        return
    text = message.text.strip()
    if not text:
        await message.reply_text("빈 메시지는 처리할 수 없어요. 다시 입력해주세요.")
        return

    await _send_typing(update)

    chat_id = update.effective_chat.id if update.effective_chat else None
    history = _get_history(context, chat_id)
    prompt = _build_prompt_with_history(history, text)

    reply_text: str

    # 1) 기본은 로컬 Gemma 로 응답
    try:
        gemma_client = _get_client(context)
        gemma_response = await gemma_client.generate(
            prompt,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
        )
        reply_text = gemma_response.text.strip()
        # Gemma 가 확실하지 않은 경우 'UNSURE' 로만 응답하도록 프롬프트에 정의해 두었음.
        if reply_text.upper() == "UNSURE":
            reply_text = ""
    except GemmaClientError:
        logger.exception("Gemma 호출 실패")
        reply_text = ""

    # 2) Gemma 가 실패했거나, 추후 '학습 필요' 패턴을 감지하면 Gemini 로 보완
    if not reply_text:
        gemini_client = _get_gemini_client(context)
        if gemini_client is None:
            await message.reply_text(
                "현재 로컬 모델과 외부 Gemini 모두 응답을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요."
            )
            return

        try:
            gemini_response = await gemini_client.generate(
                prompt,
                system_prompt=DEFAULT_SYSTEM_PROMPT,
            )
            reply_text = gemini_response.text
        except GeminiClientError:
            logger.exception("Gemini 호출 실패")
            await message.reply_text(
                "질문을 처리하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            )
            return

    await message.reply_text(reply_text)
    _update_history(context, chat_id, text, reply_text)

    # 3) 상황/텍스트에 맞춰 스티커/짤/GIF 를 자동으로 추천 (확률/토글 기반)
    lowered = text.lower()
    reaction_query = _infer_reaction_query(text)
    reaction_category = _infer_reaction_category(text)
    explicit_media_request = any(
        keyword in lowered for keyword in ("gif", "짤", "밈", "움짤", "사진", "이미지", "그림")
    )

    media_enabled = _get_media_enabled(context)
    if not media_enabled:
        return

    # 그룹/프라이빗에 따라 미디어 반응 확률을 다르게 적용
    is_group = (update.effective_chat and update.effective_chat.type != "private")
    media_prob = MEDIA_PROB_GROUP if is_group else MEDIA_PROB_PRIVATE
    if not explicit_media_request:
        # 명시 요구 없으면 확률 기반으로만 반응
        if random.random() > media_prob:
            return

    if not reaction_query and not explicit_media_request and not reaction_category:
        return

    # 3-1) 먼저 카테고리별로 저장된 스티커가 있으면 그것부터 사용
    sticker_store = _get_sticker_store(context)
    if sticker_store is not None and reaction_category is not None and message:
        allowed_users = _get_allowed_users(context)
        sticker_id = sticker_store.get_random_filtered(
            reaction_category,
            allowed_user_ids=allowed_users,
        )
        if sticker_id:
            try:
                await message.reply_sticker(sticker=sticker_id)
                return
            except Exception:  # pragma: no cover - best effort
                logger.exception("텔레그램 스티커 전송 실패")

    # 3-2) 스티커가 없으면 Tenor 에서 GIF 검색
    media_client = _get_media_client(context)
    if media_client is None:
        return

    query = reaction_query or text
    try:
        result = await media_client.search_gif(query)
    except MediaClientError:
        logger.exception("미디어(GIF) 검색 실패")
        return

    if result and message:
        try:
            await message.reply_animation(animation=result.url)
        except Exception:  # pragma: no cover - best effort
            logger.exception("텔레그램 GIF 전송 실패")


async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """사용자가 보낸 스티커를 보고, 상황에 맞는 카테고리로 분류해 저장합니다."""

    message = update.message
    if not message or not message.sticker:
        return

    sticker = message.sticker
    chat_id = update.effective_chat.id if update.effective_chat else None
    user_id = update.effective_user.id if update.effective_user else None
    if chat_id is None:
        return

    # 가장 최근 텍스트 히스토리에서 카테고리를 추론해 본다.
    history = _get_history(context, chat_id)
    last_user_text = ""
    for turn in reversed(history):
        if turn.get("role") == "user":
            last_user_text = str(turn.get("text", "")).strip()
            if last_user_text:
                break

    category = _infer_reaction_category(last_user_text) if last_user_text else None
    if category is None and message.reply_to_message and message.reply_to_message.text:
        category = _infer_reaction_category(message.reply_to_message.text)

    # 카테고리 추론이 안 되더라도 'misc'로 저장해서 누락을 방지
    if not category:
        category = "misc"

    store = _get_sticker_store(context)
    if store is None:
        return

    # 단일 스티커 저장
    store.add(category, sticker.file_id, user_id=user_id)

    # 스티커 세트 전체를 같은 카테고리에 일괄 저장 (관리자가 나중에 clear 가능)
    if sticker.set_name:
        try:
            set_obj = await context.bot.get_sticker_set(name=sticker.set_name)
            file_ids = [s.file_id for s in set_obj.stickers or []]
            added = store.add_bulk(category, file_ids, user_id=user_id)
            if added:
                logger.info("스티커 세트 '%s'에서 %d개 추가 | category=%s", sticker.set_name, added, category)
        except Exception:  # pragma: no cover - best effort
            logger.exception("스티커 세트 저장 실패 | set=%s", sticker.set_name)


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear_memory", clear_memory_command))
    application.add_handler(CommandHandler("list_stickers", list_stickers_command))
    application.add_handler(CommandHandler("clear_stickers", clear_stickers_command))
    application.add_handler(CommandHandler("use_stickers", set_sticker_users_command))
    application.add_handler(CommandHandler("enable_media", enable_media_command))
    application.add_handler(CommandHandler("disable_media", disable_media_command))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    application.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

