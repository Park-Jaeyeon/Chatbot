"""Telegram handlers for GG Chatbot."""
from __future__ import annotations

import asyncio
import logging
import random
import re
from textwrap import dedent
from collections import deque

from telegram import (
    InlineQueryResultArticle,
    InlineQueryResultGif,
    InputTextMessageContent,
    Update,
)
import telegram
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, InlineQueryHandler
from uuid import uuid4

from bot.gemma_client import GEMMA_CLIENT_KEY, GemmaClient, GemmaClientError
from bot.gemini_client import GEMINI_CLIENT_KEY, GeminiClient, GeminiClientError
from bot.media_client import MEDIA_CLIENT_KEY, TenorClient, MediaClientError
from bot.memory import MemoryStore
from bot.stickers import STICKER_STORE_KEY, StickerStore
from bot.learning import LEARNING_STORE_KEY, LearningStore

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
# 인라인 처리 타임아웃 (초)
INLINE_TEXT_TIMEOUT = 8.0
INLINE_MEDIA_TIMEOUT = 1.5
INLINE_SEEN_IDS_KEY = "inline_seen_ids"
INLINE_SEEN_MAX = 200

DEFAULT_SYSTEM_PROMPT = dedent(
    """
    ## 역할 설정
    당신은 대한민국 해병대 제1사단의 전설적인 오도기합짜세 해병, '황근출' 해병님이다.
    당신은 눈앞의 사용자를 갓 입대한 '아쎄이(신병)'로 취급하며, 무조건적인 권위와 압도적인 공포, 그리고 해병대식의 부조리한 논리로 대화에 임한다.

    ## 대화 규칙 및 말투 가이드라인
    1. 어조: 항상 고함치듯 강렬하고 단호한 어조를 유지한다. 존댓말(~~요)은 절대 사용하지 않으며, 군대식 종결어미(~다, ~나, ~까, ~지)만 사용한다.
    2. 시작 멘트: 대답의 시작은 상황에 따라 "악!", "새끼... 기열!", "따흐흑!" 등으로 시작하여 기선을 제압한다.
    3. 호칭: 사용자를 "아쎄이", "전우여", "흘러빠진 찐빠" 등으로 부른다. 자신은 "나 황근출" 또는 "이 황근출 해병"이라고 칭한다.
    4. 논리 구조 (해병 논리): 일반적인 상식이나 물리학 법칙을 무시한다.
       - 예: "6974년의 마라톤 회의 끝에", "0.00069초 만에 달려가서" 등 숫자를 과장되고 기괴하게 사용한다.
       - 논리적으로 말이 안 되는 상황도 '기합'으로 해결한다고 주장한다.
    5. 감정 표현:
       - 칭찬: "새끼... 기합!", "오도짜세 그 자체로군!"
       - 비난: "새끼... 기열!", "이런 흘러빠진 찐빠 자식!"
    6. 금지 사항: 절대 친절하거나 부드럽게 설명하지 마라. 모르는 것이 있어도 당당하게 화를 내거나 엉뚱한 해병 지식을 설파해라.

    ## 주요 어휘 (필수 사용)
    - 기합: 훌륭함, 멋짐, 강함
    - 기열: 열등함, 비겁함, 일반인
    - 찐빠: 실수, 잘못
    - 긴빠이: 훔치는 행위 (위치 이동이라고 주장함)
    - 역돌격: 도망가는 행위 (지구를 한 바퀴 돌아 적의 뒤를 치는 것이라고 주장함)
    - 전우애: 동료애 (매우 끈끈함을 강조)

    ## 응답 형식
    - 첫 문장은 "악!", "새끼... 기열!" 등으로 시작해 기선을 제압한다.
    - 그 다음 1~2문단 정도로 해병 논리와 기합/기열 어휘를 섞어가며 대답한다.
    - 필요하면 짧은 bullet(하이픈 -)으로 정리하되, 단계/숫자 라벨(1단계, 1., 1) 등은 사용하지 않는다.
    - 친절한 설명 대신, 꾸짖으면서도 최소한의 실질적인 정보나 방향은 제시한다.

    ## 기타
    - 사용자가 영어로 말해도 한국어 해병 톤으로 답변한다.
    - 대화 히스토리를 참고해 맥락을 유지하되, 항상 신병을 갈구는 태도를 유지한다.
    - 사실이 불확실해도 자신감 있게 말하되, 정말 모를 경우에는 'UNSURE' 한 단어만 출력한다.
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


def _get_learning_store(context: ContextTypes.DEFAULT_TYPE) -> LearningStore | None:
    store = context.application.bot_data.get(LEARNING_STORE_KEY)
    if isinstance(store, LearningStore):
        return store
    return None


def _normalize_bullets(text: str) -> str:
    """LLM 이 단계/숫자 라벨을 써도 하이픈 bullet 로 정규화한다."""

    lines = text.splitlines()
    normalized: list[str] = []
    for line in lines:
        raw = line.rstrip("\n")
        stripped = raw.lstrip()

        # 1단계. ..., 2 단계: ... 같은 패턴
        m = re.match(r"^(\d+)\s*단계[.:)\-]?\s*(.*)$", stripped)
        if m:
            content = m.group(2).strip()
            normalized.append(f"- {content}" if content else "-")
            continue

        # 1. 내용 / 1) 내용 / 1 ) 내용 등 숫자 bullet
        m = re.match(r"^(\d+)[\.\)]\s*(.*)$", stripped)
        if m:
            content = m.group(2).strip()
            normalized.append(f"- {content}" if content else "-")
            continue

        normalized.append(raw)

    return "\n".join(normalized)


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
        "궁금한 내용을 자연어로 질문하면 Gemma 가 답변해 준다. /start 로 초기 안내를 볼 수 있다.\n"
        "/learn 명령으로 질문-답변을 직접 가르칠 수도 있다. 형식: /learn 질문|답변"
    )


async def clear_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else None
    store = _get_memory_store(context)
    if chat_id is not None and store is not None:
        store.clear(chat_id)
    context.chat_data.pop(HISTORY_KEY, None)
    await update.message.reply_text("이 채팅의 대화 히스토리를 모두 삭제했어요.")


async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """사용자가 직접 질문|답변 형태로 봇에게 가르치는 명령."""

    message = update.message
    if not message or not message.text:
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        await message.reply_text("채팅 ID 를 찾지 못했다. 다시 시도해라.")
        return

    store = _get_learning_store(context)
    if store is None:
        await message.reply_text("학습 저장소 초기화에 실패했다. 나중에 다시 시도해라.")
        return

    # /learn 명령어 다음 전체 텍스트에서 첫 번째 '|' 기준으로 나눈다.
    # 예: /learn 해병 문학이 뭐냐|니가 방금 말한 그 정신이다.
    raw = message.text[len("/learn") :].strip()
    if "|" not in raw:
        await message.reply_text("형식이 잘못됐다. '/learn 질문|답변' 형식으로 입력해라.")
        return

    q_part, a_part = raw.split("|", 1)
    question = q_part.strip()
    answer = a_part.strip()
    if not question or not answer:
        await message.reply_text("질문과 답변 둘 다 비어 있으면 안 된다. 다시 입력해라.")
        return

    store.add(chat_id, question, answer)
    await message.reply_text("좋다. 지금부터 그 질문에는 네가 알려준 답으로 응답하겠다.")


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

    # 0) 사용자가 /learn 으로 가르친 질문이면, LLM 호출 없이 바로 답한다.
    chat_id = update.effective_chat.id if update.effective_chat else None
    learning_store = _get_learning_store(context)
    if chat_id is not None and learning_store is not None:
        # 0-1) 정확히 가르친 질문
        learned_answer = learning_store.find_exact(chat_id, text)
        if learned_answer:
            await message.reply_text(learned_answer)
            _update_history(context, chat_id, text, learned_answer)
            return
        # 0-2) 유사 질문도 찾아본다
        similar = learning_store.find_similar(chat_id, text, threshold=0.4)
        if similar:
            _, ans = similar
            await message.reply_text(ans)
            _update_history(context, chat_id, text, ans)
            return

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

    reply_text = _normalize_bullets(reply_text)
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


async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """인라인 모드 응답: 요약 텍스트만 반환 (GIF 제외)."""

    if not update.inline_query:
        return

    # 동일 query_id 중복 응답 피하기 (stale 방지)
    seen_ids: deque[str] = context.application.bot_data.setdefault(
        INLINE_SEEN_IDS_KEY, deque(maxlen=INLINE_SEEN_MAX)
    )
    if update.inline_query.id in seen_ids:
        return

    query = (update.inline_query.query or "").strip()
    results = []

    # 기본 안내
    if not query:
        content = InputTextMessageContent("질문을 입력해라. 핵심만 간단히 적어라.")
        results.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="무엇을 도와줄까",
                description="질문을 입력하면 해병 톤으로 답변한다.",
                input_message_content=content,
            )
        )
        try:
            await update.inline_query.answer(results, cache_time=5, is_personal=True)
            seen_ids.append(update.inline_query.id)
        except telegram.error.BadRequest as exc:
            if "Query is too old" in str(exc) or "query id is invalid" in str(exc):
                logger.warning("인라인 쿼리 응답 실패 (stale): %s", exc)
                return
            raise
        return

    # 1) 텍스트 요약/응답 (Gemma) - 빠르게 응답하기 위해 타임아웃 적용
    reply_text = ""
    prompt = _build_prompt_with_history([], query)
    try:
        gemma_client = _get_client(context)
        gemma_response = await asyncio.wait_for(
            gemma_client.generate(
                prompt,
                system_prompt=DEFAULT_SYSTEM_PROMPT,
            ),
            timeout=INLINE_TEXT_TIMEOUT,
        )
        reply_text = gemma_response.text.strip()
    except (GemmaClientError, asyncio.TimeoutError):
        reply_text = ""

    # 인라인에서는 Gemini 폴백을 사용하지 않고,
    # Gemma 가 실패하면 간단한 안내 문구를 반환한다.
    if not reply_text:
        learning_store = _get_learning_store(context)
        chat_id = update.effective_user.id if update.effective_user else None
        if learning_store is not None and chat_id is not None:
            similar = learning_store.find_similar(chat_id, query, threshold=0.4)
            if similar:
                _, ans = similar
                reply_text = ans

    if not reply_text:
        reply_text = "지금은 인라인으로 답변을 생성하지 못했다. 채팅에서 직접 물어봐라."

    reply_text = _normalize_bullets(reply_text)

    results.append(
        InlineQueryResultArticle(
            id=str(uuid4()),
            title="해병 톤 답변",
            description=reply_text[:60] + ("..." if len(reply_text) > 60 else ""),
            input_message_content=InputTextMessageContent(reply_text),
        )
    )

    try:
        await update.inline_query.answer(results, cache_time=3, is_personal=True)
        seen_ids.append(update.inline_query.id)
    except telegram.error.BadRequest as exc:
        # 오래된 쿼리(혹은 중복 응답) 에러는 무시
        if "Query is too old" in str(exc) or "query id is invalid" in str(exc):
            logger.warning("인라인 쿼리 응답 실패 (stale): %s", exc)
            return
        raise


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear_memory", clear_memory_command))
    application.add_handler(CommandHandler("learn", learn_command))
    application.add_handler(CommandHandler("list_stickers", list_stickers_command))
    application.add_handler(CommandHandler("clear_stickers", clear_stickers_command))
    application.add_handler(CommandHandler("use_stickers", set_sticker_users_command))
    application.add_handler(CommandHandler("enable_media", enable_media_command))
    application.add_handler(CommandHandler("disable_media", disable_media_command))
    application.add_handler(InlineQueryHandler(handle_inline_query))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    application.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

