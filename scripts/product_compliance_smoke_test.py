from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.partner_share_service import generate_partner_share_asset
from app.services.product_compliance_service import backfill_product_compliance
from app.services.product_service import get_products


def main() -> int:
    db = SessionLocal()
    try:
        backfill = backfill_product_compliance(db)

        visible = get_products(db, page=1, page_size=20)
        hard_block = (
            db.query(Product)
            .filter(Product.compliance_level == "hard_block", Product.status == "active")
            .order_by(Product.id.desc())
            .first()
        )

        blocked_share = None
        if hard_block:
            try:
                generate_partner_share_asset(
                    db,
                    wechat_openid=f"smoke_share_block_{int(time.time())}",
                    product_id=hard_block.id,
                )
                blocked_share = {"product_id": hard_block.id, "unexpected": "share_succeeded"}
            except Exception as exc:
                blocked_share = {"product_id": hard_block.id, "blocked_error": str(exc)}

        print(json.dumps({
            "backfill": backfill,
            "visible_total": visible["total"],
            "hard_block_product": {
                "id": hard_block.id,
                "title": hard_block.title,
                "compliance_level": hard_block.compliance_level,
                "allow_partner_share": hard_block.allow_partner_share,
            } if hard_block else None,
            "blocked_share": blocked_share,
        }, ensure_ascii=False, indent=2)[:6000])

        if hard_block and blocked_share and "blocked_error" not in blocked_share:
            print("FAIL: hard block product should not be shareable")
            return 2

        print("PASS: product compliance smoke test ok")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
