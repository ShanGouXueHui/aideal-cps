from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.main import app
from app.models.click_log import ClickLog
from app.models.product import Product
from app.services.user_service import get_or_create_user_by_openid


def main() -> int:
    # 预备数据
    db = SessionLocal()
    try:
        get_or_create_user_by_openid("test_user_openid")

        product = (
            db.query(Product)
            .filter(
                Product.status == "active",
                Product.short_url.isnot(None),
                Product.short_url != "",
                Product.merchant_recommendable.is_(True),
            )
            .order_by(Product.updated_at.desc())
            .first()
        )
        if not product:
            print("FAIL: no eligible product found")
            return 1

        before_count = db.query(ClickLog).count()
        product_id = product.id
    finally:
        db.close()

    client = TestClient(app)
    response = client.get(
        f"/api/promotion/redirect?wechat_openid=test_user_openid&product_id={product_id}&scene=wechat_reply&slot=1",
        follow_redirects=False,
        headers={
            "user-agent": "promotion-smoke-test",
            "referer": "https://aidealfy.kindafeelfy.cn/",
        },
    )

    print("status_code=", response.status_code)
    print("location=", response.headers.get("location"))

    # 用全新 session 读取，避免读到旧事务快照
    db2 = SessionLocal()
    try:
        after_count = db2.query(ClickLog).count()
        latest = db2.query(ClickLog).order_by(ClickLog.id.desc()).first()

        payload = {
            "before_count": before_count,
            "after_count": after_count,
            "click_log_id": latest.id if latest else None,
            "trace_id": latest.trace_id if latest else None,
            "scene": latest.scene if latest else None,
            "slot": latest.slot if latest else None,
            "final_url": latest.final_url if latest else None,
            "short_url": latest.short_url if latest else None,
            "wechat_openid": latest.wechat_openid if latest else None,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))

        if response.status_code not in (302, 307):
            print("FAIL: redirect status invalid")
            return 2
        if not response.headers.get("location"):
            print("FAIL: location header missing")
            return 3
        if after_count != before_count + 1:
            print("FAIL: click log count did not increase")
            return 4
        if not latest:
            print("FAIL: latest click log missing")
            return 5
        if latest.scene != "wechat_reply" or latest.slot != 1:
            print("FAIL: click log scene/slot mismatch")
            return 6
        if latest.wechat_openid != "test_user_openid":
            print("FAIL: click log wechat_openid mismatch")
            return 7
        if not latest.final_url:
            print("FAIL: click log final_url missing")
            return 8

        print("PASS: promotion redirect smoke test ok")
        return 0
    finally:
        db2.close()


if __name__ == "__main__":
    raise SystemExit(main())
