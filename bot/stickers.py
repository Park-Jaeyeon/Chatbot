"""Simple storage for reaction stickers by category."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Sequence

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

    def _load_meta(self) -> Dict[str, Dict[str, List[int]]]:
        """메타 정보 저장용 특수 키를 별도로 관리한다."""
        # _meta 구조: {"owners": {file_id: [user_ids...]}}
        data = self._read_all()
        meta_raw = data.get("_meta")
        owners: Dict[str, List[int]] = {}
        if isinstance(meta_raw, dict):
            meta_owners = meta_raw.get("owners")
            if isinstance(meta_owners, dict):
                for fid, lst in meta_owners.items():
                    if isinstance(lst, list):
                        owners[str(fid)] = [int(x) for x in lst if isinstance(x, (int, float, str))]
        return owners

    def _write_meta(self, data: Dict[str, List[str]], owners: Dict[str, List[int]]) -> None:
        # data 에 _meta 키를 다시 주입
        data["_meta"] = {"owners": owners}
        self._write_all(data)

    def add(self, category: str, file_id: str, *, user_id: Optional[int] = None) -> None:
        data = self._read_all()
        owners = self._load_meta()
        bucket = data.setdefault(category, [])
        if file_id not in bucket:
            bucket.append(file_id)
        if user_id is not None:
            arr = owners.setdefault(file_id, [])
            if user_id not in arr:
                arr.append(user_id)
        self._write_meta(data, owners)

    def get_random(self, category: str) -> Optional[str]:
        data = self._read_all()
        bucket = data.get(category) or []
        if not bucket:
            return None
        return random.choice(bucket)

    def list_counts(self) -> Dict[str, int]:
        data = self._read_all()
        return {k: len(v) for k, v in data.items() if isinstance(v, list) and k != "_meta"}

    def list_counts_with_owners(self) -> Dict[str, Dict[str, object]]:
        """카테고리별 스티커 개수와 owner 빈도를 반환."""
        data = self._read_all()
        owners = self._load_meta()
        result: Dict[str, Dict[str, object]] = {}
        for cat, items in data.items():
            if not isinstance(items, list) or cat == "_meta":
                continue
            owner_counts: Dict[int, int] = {}
            for fid in items:
                for uid in owners.get(fid, []):
                    owner_counts[uid] = owner_counts.get(uid, 0) + 1
            result[cat] = {
                "count": len(items),
                "owners": owner_counts,
            }
        return result

    def clear_category(self, category: str) -> None:
        data = self._read_all()
        owners = self._load_meta()
        removed = data.pop(category, None) if category in data else None
        if removed and isinstance(removed, list):
            for fid in removed:
                owners.pop(str(fid), None)
        self._write_meta(data, owners)

    def add_bulk(self, category: str, file_ids: List[str], *, user_id: Optional[int] = None) -> int:
        """대량 스티커 추가. 이미 있는 것은 건너뛰고 추가된 개수를 반환."""
        data = self._read_all()
        owners = self._load_meta()
        bucket = data.setdefault(category, [])
        added = 0
        for fid in file_ids:
            if fid not in bucket:
                bucket.append(fid)
                added += 1
            if user_id is not None:
                arr = owners.setdefault(fid, [])
                if user_id not in arr:
                    arr.append(user_id)
        if added or user_id is not None:
            self._write_meta(data, owners)
        return added

    def get_random_filtered(self, category: str, *, allowed_user_ids: Optional[Sequence[int]] = None) -> Optional[str]:
        """특정 사용자 목록의 스티커만 선택(목록 없으면 전체에서 선택)."""
        data = self._read_all()
        owners = self._load_meta()
        bucket = data.get(category) or []
        if not bucket:
            return None
        # 필터가 없으면 바로 랜덤
        if not allowed_user_ids:
            return random.choice(bucket)

        allowed = set(int(u) for u in allowed_user_ids)
        filtered = [fid for fid in bucket if allowed.intersection(owners.get(fid, []))]
        if filtered:
            return random.choice(filtered)
        # 필터에 맞는 스티커가 없으면 None
        return None
