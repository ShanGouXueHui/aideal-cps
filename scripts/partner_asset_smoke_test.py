from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.partner_account_service import enroll_partner_by_openid
from app.services.partner_share_service import generate_partner_share_asset, open_partner_buy_link


def main() -> int:
    db = SessionLocal()
    try:
        product = (
            db.query(Product)
            .filter(
                Product.status == "active",
                Product.material_url.isnot(None),
                Product.material_url != "",
            )
            .order_by(Product.updated_at.desc())
            .first()
        )
        if not product:
            print("FAIL: no active product with material_url found")
            return 1

        partner = enroll_partner_by_openid(db, "test_partner_openid")
        asset = generate_partner_share_asset(
            db,
            wechat_openid="test_partner_openid",
            product_id=product.id,
            rank_tags="高佣榜 | 热销候选",
        )
        click = open_partner_buy_link(
            db,
            asset_token=asset["asset_token"],
            request_source="smoke_test",
            client_ip="127.0.0.1",
            user_agent="smoke-test",
            referer=None,
        )

        print(json.dumps({
            "partner": partner,
            "asset": asset,
            "click": click,
        }, ensure_ascii=False, indent=2)[:7000])

        required = [
            "buy_url",
            "short_url",
            "buy_qr_svg_path",
            "share_qr_svg_path",
            "poster_svg_path",
            "buy_copy",
            "share_copy",
        ]
        for key in required:
            if not asset.get(key):
                print(f"FAIL: {key} missing")
                return 10

        for key in ("buy_qr_svg_path", "share_qr_svg_path", "poster_svg_path"):
            file_path = PROJECT_ROOT / asset[key]
            if not file_path.exists():
                print(f"FAIL: file missing -> {file_path}")
                return 11

        if not click.get("redirect_url"):
            print("FAIL: redirect_url missing")
            return 12

        print("PASS: partner asset smoke test ok")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
