"""Simple per-chat learning store (question -> answer overrides)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re


LEARNING_STORE_KEY = "learning_store"


class LearningStore:
    """JSON 파일 기반의 간단한 학습 저장소.

    구조:
    {
      "<chat_id>": [
        {"q": "<질문 텍스트>", "a": "<답변 텍스트>"},
        ...
      ]
    }
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        if self._path.parent:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> Dict[str, List[dict]]:
        if not self._path.exists():
            return {}
        try:
            raw = self._path.read_text(encoding="utf-8")
            if not raw.strip():
                return {}
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): list(v) for k, v in data.items() if isinstance(v, list)}
            return {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_all(self, data: Dict[str, List[dict]]) -> None:
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        text = json.dumps(data, ensure_ascii=False, indent=2)
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(self._path)

    def add(self, chat_id: int, question: str, answer: str) -> None:
        data = self._read_all()
        key = str(chat_id)
        entries = data.setdefault(key, [])
        entry = {"q": question.strip(), "a": answer.strip()}
        # 같은 질문이 있으면 덮어쓰기
        for idx, item in enumerate(entries):
            if item.get("q") == entry["q"]:
                entries[idx] = entry
                break
        else:
            entries.append(entry)
        self._write_all(data)

    def find_exact(self, chat_id: int, question: str) -> Optional[str]:
        data = self._read_all()
        entries = data.get(str(chat_id)) or []
        q_norm = question.strip()
        for item in entries:
            if item.get("q") == q_norm:
                return str(item.get("a", "")).strip() or None
        return None

    def list_questions(self, chat_id: int) -> List[str]:
        data = self._read_all()
        entries = data.get(str(chat_id)) or []
        return [str(item.get("q", "")) for item in entries if item.get("q")]

    def clear_chat(self, chat_id: int) -> None:
        data = self._read_all()
        if str(chat_id) in data:
            data.pop(str(chat_id), None)
            self._write_all(data)

    # --- 유사도 검색 유틸 ---
    @staticmethod
    def _tokenize(text: str) -> List[str]:
        clean = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", text.lower())
        return [t for t in clean.split() if t]

    @classmethod
    def _similarity(cls, a: str, b: str) -> float:
        ta = set(cls._tokenize(a))
        tb = set(cls._tokenize(b))
        if not ta or not tb:
            return 0.0
        inter = len(ta & tb)
        union = len(ta | tb)
        return inter / union if union else 0.0

    def find_similar(self, chat_id: int, question: str, *, threshold: float = 0.5) -> Optional[Tuple[str, str]]:
        """유사 질문을 찾아 (질문, 답변) 반환. 없으면 None."""

        data = self._read_all()
        entries = data.get(str(chat_id)) or []
        best: Tuple[str, str, float] | None = None  # q, a, score
        for item in entries:
            q = str(item.get("q", "")).strip()
            a = str(item.get("a", "")).strip()
            if not q or not a:
                continue
            score = self._similarity(question, q)
            if score >= threshold and (best is None or score > best[2]):
                best = (q, a, score)
        if best:
            return best[0], best[1]
        return None
