from __future__ import annotations

import json
from pathlib import Path


_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "wechat_menu_entries.json"


def load_wechat_menu_entries() -> dict:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def get_menu_entry_map() -> dict[str, dict]:
    data = load_wechat_menu_entries()
    return {item["key"]: item for item in data.get("menu_entries", [])}
