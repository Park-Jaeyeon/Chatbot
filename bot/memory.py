"""Simple persistent memory store for user conversations."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List


class MemoryStore:
    """Abstract interface for conversation memory backends."""

    def load(self, chat_id: int) -> List[dict[str, str]]:
        raise NotImplementedError

    def save(self, chat_id: int, history: List[dict[str, str]]) -> None:
        raise NotImplementedError


class JsonFileMemoryStore(MemoryStore):
    """Very small JSON-file based memory store.

    Stores a mapping of chat_id -> list[{"role": ..., "text": ...}] on disk.
    Intended only for local experimentation, not for production scale.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        # Ensure parent directory exists (e.g. ROOT_DIR / "data")
        if self._path.parent:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> Dict[str, list[dict[str, str]]]:
        if not self._path.exists():
            return {}

        try:
            raw = self._path.read_text(encoding="utf-8")
            if not raw.strip():
                return {}
            data = json.loads(raw)
            if isinstance(data, dict):
                return {
                    str(k): list(v) for k, v in data.items() if isinstance(v, list)
                }
            return {}
        except (OSError, json.JSONDecodeError):
            # If the file is corrupted or unreadable, start fresh.
            return {}

    def _write_all(self, data: Dict[str, list[dict[str, str]]]) -> None:
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        text = json.dumps(data, ensure_ascii=False, indent=2)
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(self._path)

    def load(self, chat_id: int) -> List[dict[str, str]]:
        key = str(chat_id)
        with self._lock:
            data = self._read_all()
            return list(data.get(key, []))

    def save(self, chat_id: int, history: List[dict[str, str]]) -> None:
        key = str(chat_id)
        with self._lock:
            data = self._read_all()
            data[key] = list(history)
            self._write_all(data)

