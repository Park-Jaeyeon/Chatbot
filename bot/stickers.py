"""Simple storage for reaction stickers by category."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List, Optional

STICKER_STORE_KEY = "sticker_store"


class StickerStore:
    """JSON 파일에 카테고리별 스티커 file_id 를 저장/로딩하는 간단한 저장소."""

    def __init__(self, path: Path) -> None:
        self._path = path
        if self._path.parent:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> Dict[str, List[str]]:
        if not self._path.exists():
            return {}
        try:
            raw = self._path.read_text(encoding="utf-8")
            if not raw.strip():
                return {}
            data = json.loads(raw)
            if isinstance(data, dict):
                return {
                    str(k): [str(vv) for vv in v]
                    for k, v in data.items()
                    if isinstance(v, list)
                }
            return {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_all(self, data: Dict[str, List[str]]) -> None:
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        text = json.dumps(data, ensure_ascii=False, indent=2)
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(self._path)

    def add(self, category: str, file_id: str) -> None:
        data = self._read_all()
        bucket = data.setdefault(category, [])
        if file_id not in bucket:
            bucket.append(file_id)
            self._write_all(data)

    def get_random(self, category: str) -> Optional[str]:
        data = self._read_all()
        bucket = data.get(category) or []
        if not bucket:
            return None
        return random.choice(bucket)

