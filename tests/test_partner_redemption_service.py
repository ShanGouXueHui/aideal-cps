from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.partner_account import PartnerAccount
from app.models.partner_point_redemption import PartnerPointRedemption
from app.models.partner_reward_ledger import PartnerRewardLedger
from app.models.user import User
from app.services.partner_redemption_service import (
    commit_partner_redemption,
    get_partner_redemption_history,
    list_partner_redemption_options,
    preview_partner_redemption,
)
from app.services.partner_reward_service import record_partner_reward_event


def test_partner_redemption_flow_activation_fee():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            PartnerAccount.__table__,
            PartnerRewardLedger.__table__,
            PartnerPointRedemption.__table__,
        ],
    )
    db = SessionLocal()

    record_partner_reward_event(
        db,
        wechat_openid="wx_redeem_user",
        event_type="settled",
        commission_amount=1000,
        order_ref="settled-001",
    )

    options = list_partner_redemption_options(db, wechat_openid="wx_redeem_user")
    assert options["available_points"] == 400.0

    preview = preview_partner_redemption(
        db,
        wechat_openid="wx_redeem_user",
        item_code="partner_activation_fee",
        use_points=100,
    )
    assert preview["points_used"] == 100.0
    assert preview["cash_due_rmb"] == 0.0
    assert preview["status_hint"] == "completed"

    commit = commit_partner_redemption(
        db,
        wechat_openid="wx_redeem_user",
        item_code="partner_activation_fee",
        use_points=100,
        note="activation by points",
    )
    assert commit["status"] == "completed"
    assert commit["activation_fee_paid"] is True
    assert commit["points_used"] == 100.0

    history = get_partner_redemption_history(db, wechat_openid="wx_redeem_user")
    assert history["activation_fee_paid"] is True
    assert len(history["items"]) == 1
    assert history["items"][0]["item_code"] == "partner_activation_fee"
