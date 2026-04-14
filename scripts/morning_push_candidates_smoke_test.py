from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.morning_push_service import generate_morning_push_candidates
from app.services.user_profile_service import update_user_profile_from_text


def main() -> int:
    db = SessionLocal()
    try:
        sample_product = (
            db.query(Product)
            .filter(
                Product.status == "active",
                Product.merchant_recommendable.is_(True),
                Product.short_url.isnot(None),
                Product.short_url != "",
            )
            .order_by(Product.updated_at.desc())
            .first()
        )
        if not sample_product:
            print("FAIL: no eligible product found")
            return 1

        category = sample_product.category_name or "牙膏"
        update_user_profile_from_text(db, "test_user_openid", f"我想买{category}，想要便宜一点")

        rows = generate_morning_push_candidates(db, current_hour=8, limit=5)
        print(json.dumps(rows, ensure_ascii=False, indent=2)[:4000])

        if not rows:
            print("FAIL: no morning push candidates generated")
            return 2

        print("PASS: morning push candidates smoke test ok")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
