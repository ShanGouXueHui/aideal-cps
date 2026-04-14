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
from app.services.partner_center_service import get_partner_center
from app.services.partner_redemption_service import commit_partner_redemption
from app.services.partner_reward_service import record_partner_reward_event
from app.services.partner_share_service import generate_partner_share_asset


def main() -> int:
    db = SessionLocal()
    try:
        openid = f"test_partner_center_openid_{int(time.time())}"

        product = (
            db.query(Product)
            .filter(
                Product.status == "active",
                Product.material_url.isnot(None),
                Product.material_url != "",
            )
            .order_by(Product.updated_at.desc(), Product.id.desc())
            .first()
        )
        if not product:
            print("FAIL: no active shareable product found")
            return 2

        record_partner_reward_event(
            db,
            wechat_openid=openid,
            event_type="settled",
            commission_amount=1000,
            order_ref="center-settled-001",
            note="seed points for center smoke",
        )

        generate_partner_share_asset(
            db,
            wechat_openid=openid,
            product_id=product.id,
            rank_tags="高佣榜 | 可分享",
        )

        commit_partner_redemption(
            db,
            wechat_openid=openid,
            item_code="partner_activation_fee",
            use_points=100,
            note="center smoke activation",
        )

        center = get_partner_center(db, wechat_openid=openid)

        print(json.dumps({
            "openid": openid,
            "center": center,
        }, ensure_ascii=False, indent=2)[:7000])

        if center["profile"]["activation_fee_paid"] is not True:
            print("FAIL: activation fee status invalid")
            return 3
        if center["reward_overview"]["available_points"] <= 0:
            print("FAIL: available points invalid")
            return 4
        if len(center["recent_assets"]) == 0:
            print("FAIL: recent assets empty")
            return 5
        if len(center["recent_shareable_products"]) == 0:
            print("FAIL: recent shareable products empty")
            return 6

        print("PASS: partner center smoke test ok")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
