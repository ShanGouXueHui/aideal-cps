from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


POSTER_STYLE_FILE = Path(__file__).resolve().parents[2] / "config" / "poster_card_style.json"


@lru_cache(maxsize=1)
def load_poster_card_style() -> dict:
    with POSTER_STYLE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)
