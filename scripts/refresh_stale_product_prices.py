from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# PRICE_SCRIPT_SYSPATH_GATE

from datetime import datetime, timedelta
import json
from pathlib import Path

from sqlalchemy import text

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.jd_price_freshness_service import refresh_stale_recommendation_pool_prices

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "jd_price_refresh_policy.json"


def load_policy() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}



def main() -> None:
    policy = load_policy()
    limit = int(policy.get("background_limit_per_run") or 50)

    db = SessionLocal()
    try:
        result = refresh_stale_recommendation_pool_prices(db, limit=limit)
        db.commit()
        print(result)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
