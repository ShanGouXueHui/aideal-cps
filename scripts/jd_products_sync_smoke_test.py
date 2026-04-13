from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.services.jd_product_sync_service import sync_jd_products


def main() -> int:
    db = SessionLocal()
    try:
        result = sync_jd_products(
            db,
            elite_id=129,
            limit=3,
            page_index=1,
            page_size=5,
            with_short_links=True,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["total"] <= 0:
            print("FAIL: sync returned zero rows")
            return 1
        print("PASS: jd products sync ok")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
