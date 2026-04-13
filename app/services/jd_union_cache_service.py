from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class JDUnionCacheService:
    def __init__(self, base_dir: str = "data/jd_cache", default_ttl_seconds: int = 900) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl_seconds = default_ttl_seconds

    def _key_to_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.base_dir / f"{digest}.json"

    def get(self, key: str, ttl_seconds: int | None = None) -> Any | None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        path = self._key_to_path(key)
        if not path.exists():
            return None

        raw = json.loads(path.read_text(encoding="utf-8"))
        created_at = raw.get("created_at", 0)
        if time.time() - created_at > ttl:
            return None
        return raw.get("payload")

    def set(self, key: str, payload: Any) -> None:
        path = self._key_to_path(key)
        wrapper = {
            "created_at": time.time(),
            "payload": payload,
        }
        path.write_text(json.dumps(wrapper, ensure_ascii=False, indent=2), encoding="utf-8")
