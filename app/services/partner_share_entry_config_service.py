from __future__ import annotations

import json
from pathlib import Path


_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "partner_share_entry_rules.json"


def load_partner_share_entry_rules() -> dict:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
