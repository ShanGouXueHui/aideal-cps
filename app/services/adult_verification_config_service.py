from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@lru_cache(maxsize=1)
def load_adult_verification_rules() -> dict:
    path = CONFIG_DIR / "adult_verification_rules.json"
    return json.loads(path.read_text(encoding="utf-8"))
