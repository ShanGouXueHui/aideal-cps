from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.services.partner_reward_service import (
    get_partner_reward_overview,
    record_partner_reward_event,
)


def main() -> int:
    db = SessionLocal()
    try:
        openid = f"test_partner_reward_openid_{int(time.time())}"

        steps = []
        steps.append(
            record_partner_reward_event(
                db,
                wechat_openid=openid,
                event_type="estimated",
                commission_amount=100,
                order_ref="smoke-est-001",
                note="estimated reward smoke",
            )
        )
        steps.append(
            record_partner_reward_event(
                db,
                wechat_openid=openid,
                event_type="settled",
                commission_amount=100000,
                order_ref="smoke-set-001",
                note="settled reward smoke",
            )
        )
        steps.append(
            record_partner_reward_event(
                db,
                wechat_openid=openid,
                event_type="reversed",
                commission_amount=20,
                order_ref="smoke-rev-001",
                note="reversed reward smoke",
                applied_share_rate=0.5,
            )
        )
        steps.append(
            record_partner_reward_event(
                db,
                wechat_openid=openid,
                event_type="redeem",
                points_delta=10,
                note="redeem reward smoke",
            )
        )

        overview = get_partner_reward_overview(db, wechat_openid=openid)

        print(json.dumps({
            "openid": openid,
            "steps": steps,
            "overview": overview,
        }, ensure_ascii=False, indent=2)[:7000])

        if overview["tier_code"] != "gold":
            print("FAIL: tier not upgraded to gold")
            return 2
        if overview["available_points"] <= 0:
            print("FAIL: available_points invalid")
            return 3
        if overview["settled_reward"] <= 0:
            print("FAIL: settled_reward invalid")
            return 4
        if overview["entry_rules"]["fee_activation_amount_rmb"] != 100:
            print("FAIL: fee activation rule missing")
            return 5
        if not overview["point_use_plan"]["supported_scenes"]:
            print("FAIL: point use plan missing")
            return 6

        print("PASS: partner reward smoke test ok")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
