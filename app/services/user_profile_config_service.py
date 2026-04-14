from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


PROFILE_RULES_FILE = Path(__file__).resolve().parents[2] / "config" / "user_profile_rules.json"
MORNING_PUSH_COPY_FILE = Path(__file__).resolve().parents[2] / "config" / "morning_push_copy.json"


@lru_cache(maxsize=1)
def load_user_profile_rules() -> dict:
    with PROFILE_RULES_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_morning_push_copy() -> dict:
    with MORNING_PUSH_COPY_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)
