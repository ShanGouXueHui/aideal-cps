from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.models.merchant_profile import MerchantProfile


def main() -> int:
    db = SessionLocal()
    try:
        rows = (
            db.query(MerchantProfile)
            .order_by(MerchantProfile.merchant_health_score.desc())
            .limit(10)
            .all()
        )
        payload = [
            {
                "shop_id": row.shop_id,
                "shop_name": row.shop_name,
                "merchant_health_score": row.merchant_health_score,
                "risk_flags": row.risk_flags,
                "recommendable": row.recommendable,
            }
            for row in rows
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if not payload:
            print("FAIL: no merchant profiles found")
            return 1
        print("PASS: merchant profile smoke test ok")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
