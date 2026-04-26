from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# NIGHTLY_SYSPATH_GATE

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.services.catalog_refresh_service import run_nightly_catalog_refresh


def main() -> int:
    db = SessionLocal()
    try:
        result = run_nightly_catalog_refresh(db)
        print(json.dumps(result, ensure_ascii=False, indent=2)[:12000])
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())


# PRICE_FRESHNESS_AFTER_RECOMMENDATION_GATE
if __name__ == "__main__":
    try:
        from app.core.db import SessionLocal
        from app.services.jd_price_freshness_service import refresh_stale_recommendation_pool_prices

        db = SessionLocal()
        try:
            result = refresh_stale_recommendation_pool_prices(db)
            db.commit()
            print("price_freshness_after_recommendation =", result)
        finally:
            db.close()
    except Exception as exc:
        print("price_freshness_after_recommendation_failed =", repr(exc))
