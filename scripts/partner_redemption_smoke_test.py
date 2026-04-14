from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.services.partner_redemption_service import (
    commit_partner_redemption,
    get_partner_redemption_history,
    list_partner_redemption_options,
    preview_partner_redemption,
)
from app.services.partner_reward_service import record_partner_reward_event


def main() -> int:
    db = SessionLocal()
    try:
        openid = f"test_partner_redeem_openid_{int(time.time())}"

        record_partner_reward_event(
            db,
            wechat_openid=openid,
            event_type="settled",
            commission_amount=1000,
            order_ref="redeem-settled-001",
            note="seed points for redemption smoke",
        )

        options = list_partner_redemption_options(db, wechat_openid=openid)
        preview = preview_partner_redemption(
            db,
            wechat_openid=openid,
            item_code="partner_activation_fee",
            use_points=100,
        )
        commit = commit_partner_redemption(
            db,
            wechat_openid=openid,
            item_code="partner_activation_fee",
            use_points=100,
            note="smoke activation fee by points",
        )
        history = get_partner_redemption_history(db, wechat_openid=openid)

        print(json.dumps({
            "openid": openid,
            "options": options,
            "preview": preview,
            "commit": commit,
            "history": history,
        }, ensure_ascii=False, indent=2)[:7000])

        if options["available_points"] <= 0:
            print("FAIL: no available points")
            return 2
        if preview["cash_due_rmb"] != 0.0:
            print("FAIL: activation fee should be fully offset by 100 points")
            return 3
        if commit["activation_fee_paid"] is not True:
            print("FAIL: activation fee not marked paid")
            return 4
        if len(history["items"]) != 1:
            print("FAIL: redemption history missing")
            return 5

        print("PASS: partner redemption smoke test ok")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
