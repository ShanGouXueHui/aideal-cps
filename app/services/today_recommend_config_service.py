from __future__ import annotations

import json
from pathlib import Path


_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "today_recommend_rules.json"


def load_today_recommend_rules() -> dict:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
