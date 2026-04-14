from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.partner_account import PartnerAccount
from app.models.user import User
from app.services.partner_account_service import enroll_partner_by_openid


def test_enroll_partner_by_openid_is_idempotent():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[User.__table__, PartnerAccount.__table__])
    db = SessionLocal()

    first = enroll_partner_by_openid(db, "wx_partner_1")
    second = enroll_partner_by_openid(db, "wx_partner_1")

    assert first["partner_account_id"] == second["partner_account_id"]
    assert first["partner_code"] == second["partner_code"]
    assert first["tier_code"] == "partner"
