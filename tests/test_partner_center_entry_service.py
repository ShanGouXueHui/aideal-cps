from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.user import User
from app.models.partner_account import PartnerAccount
from app.services.partner_center_entry_service import get_partner_center_entry_reply


def test_partner_center_entry_reply_for_non_partner():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[User.__table__, PartnerAccount.__table__])
    db = SessionLocal()

    user = User(
        wechat_openid="wx_non_partner",
        subunionid="subunion_non_partner",
    )
    db.add(user)
    db.commit()

    reply = get_partner_center_entry_reply(db, "wx_non_partner")
    assert "还不是合伙人" in reply or "还没有开通合伙人身份" in reply
    assert "100 元开通" in reply


def test_partner_center_entry_reply_for_partner():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[User.__table__, PartnerAccount.__table__])
    db = SessionLocal()

    user = User(
        wechat_openid="wx_partner",
        subunionid="subunion_partner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    account = PartnerAccount(
        user_id=user.id,
        partner_code="pc_test_001",
        status="active",
        tier_code="partner",
        share_rate=0.5,
        activation_fee_paid=True,
        activated_via="points",
    )
    db.add(account)
    db.commit()

    reply = get_partner_center_entry_reply(db, "wx_partner")
    assert "pc_test_001" in reply
    assert "可用积分" in reply
