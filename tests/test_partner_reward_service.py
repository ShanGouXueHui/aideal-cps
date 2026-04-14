from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.partner_account import PartnerAccount
from app.models.partner_reward_ledger import PartnerRewardLedger
from app.models.user import User
from app.services.partner_reward_service import (
    get_partner_reward_overview,
    record_partner_reward_event,
)


def test_partner_reward_ledger_and_tier_upgrade():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            PartnerAccount.__table__,
            PartnerRewardLedger.__table__,
        ],
    )
    db = SessionLocal()

    estimated = record_partner_reward_event(
        db,
        wechat_openid="wx_reward_user",
        event_type="estimated",
        commission_amount=100,
        order_ref="est-001",
    )
    assert estimated["reward_base_amount"] == 40.0
    assert estimated["points_delta"] == 0.0
    assert estimated["tier_code"] == "partner"

    settled = record_partner_reward_event(
        db,
        wechat_openid="wx_reward_user",
        event_type="settled",
        commission_amount=100000,
        order_ref="set-001",
    )
    assert settled["tier_code"] == "gold"
    assert settled["share_rate"] == 0.6
    assert settled["net_settled_commission"] == 100000.0
    assert settled["lifetime_settled_commission"] == 100000.0

    reversed_event = record_partner_reward_event(
        db,
        wechat_openid="wx_reward_user",
        event_type="reversed",
        commission_amount=20,
        order_ref="rev-001",
        applied_share_rate=0.5,
    )
    assert reversed_event["commission_amount"] == -20.0
    assert reversed_event["points_delta"] == -8.0
    assert reversed_event["tier_code"] == "gold"
    assert reversed_event["lifetime_settled_commission"] == 100000.0

    redeem = record_partner_reward_event(
        db,
        wechat_openid="wx_reward_user",
        event_type="redeem",
        points_delta=10,
        note="manual redeem test",
    )
    assert redeem["points_delta"] == -10.0
    assert redeem["tier_code"] == "gold"

    overview = get_partner_reward_overview(db, wechat_openid="wx_reward_user")
    assert overview["tier_code"] == "gold"
    assert overview["estimated_reward"] == 40.0
    assert overview["settled_reward"] == 40000.0
    assert overview["reversed_reward"] == 8.0
    assert overview["redeemed_points"] == 10.0
    assert overview["available_points"] == 39982.0
    assert overview["lifetime_settled_commission"] == 100000.0
    assert overview["entry_rules"]["fee_activation_amount_rmb"] == 100
    assert overview["point_use_plan"]["cash_redemption_enabled"] is False
