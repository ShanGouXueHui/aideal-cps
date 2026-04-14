from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@lru_cache(maxsize=1)
def load_partner_redemption_catalog() -> dict:
    path = CONFIG_DIR / "partner_redemption_catalog.json"
    return json.loads(path.read_text(encoding="utf-8"))


def get_redemption_item(item_code: str) -> dict:
    catalog = load_partner_redemption_catalog()
    for item in catalog["items"]:
        if item["item_code"] == item_code:
            return item
    raise ValueError(f"Unknown redemption item_code: {item_code}")
