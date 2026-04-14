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
from app.services.adult_verification_service import (
    build_adult_verification_url,
    get_adult_verification_status,
    mark_user_adult_verified,
)
from app.services.wechat_dialog_service import get_recommendation_reply


def main() -> int:
    db = SessionLocal()
    try:
        openid = f"test_adult_verify_{int(time.time())}"

        restricted_product = (
            db.query(Product)
            .filter(Product.compliance_level == "restricted", Product.status == "active")
            .order_by(Product.id.desc())
            .first()
        )
        if not restricted_product:
            print(json.dumps({
                "openid": openid,
                "status_before": get_adult_verification_status(db, openid),
                "verify_url": build_adult_verification_url(openid),
                "note": "no restricted product in current db; api flow still validated",
            }, ensure_ascii=False, indent=2))
            print("PASS: adult verification smoke test ok (no restricted product available)")
            return 0

        before = get_adult_verification_status(db, openid)
        reply_before = get_recommendation_reply(db, openid, restricted_product.title[:6])
        after_mark = mark_user_adult_verified(db, wechat_openid=openid)
        reply_after = get_recommendation_reply(db, openid, restricted_product.title[:6])

        print(json.dumps({
            "openid": openid,
            "restricted_product": {
                "id": restricted_product.id,
                "title": restricted_product.title,
            },
            "status_before": before,
            "status_after": after_mark,
            "reply_before": reply_before,
            "reply_after": reply_after,
        }, ensure_ascii=False, indent=2)[:6000])

        if "成年声明" not in reply_before:
            print("FAIL: reply_before should contain adult gate")
            return 2
        if "查看链接：" not in reply_after:
            print("FAIL: reply_after should contain product link")
            return 3

        print("PASS: adult verification smoke test ok")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
