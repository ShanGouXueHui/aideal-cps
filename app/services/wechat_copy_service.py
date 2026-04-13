from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


COPY_FILE = Path(__file__).resolve().parents[2] / "config" / "wechat_dialog_copy.json"


@lru_cache(maxsize=1)
def load_wechat_copy() -> dict:
    with COPY_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_copy(key: str) -> str:
    data = load_wechat_copy()
    value = data.get(key)
    if not isinstance(value, str):
        raise KeyError(f"wechat copy key not found or invalid: {key}")
    return value
