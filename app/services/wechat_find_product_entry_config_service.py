from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CONFIG_PATH = Path("config/wechat_find_product_entry.json")


@lru_cache(maxsize=1)
def load_find_product_entry_config() -> dict[str, Any]:
    try:
        if not CONFIG_PATH.exists():
            return {}
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_find_product_entry_copy(key: str, default: str = "") -> str:
    value = load_find_product_entry_config().get(key, default)
    if isinstance(value, str):
        return value
    return default
