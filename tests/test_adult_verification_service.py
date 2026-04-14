from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.user import User
from app.services.adult_verification_service import (
    get_adult_verification_status,
    mark_user_adult_verified,
)


def test_mark_user_adult_verified():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[User.__table__])
    db = SessionLocal()

    status_before = get_adult_verification_status(db, "wx_adult_test")
    assert status_before["adult_verified"] is False

    status_after = mark_user_adult_verified(db, wechat_openid="wx_adult_test")
    assert status_after["adult_verified"] is True
    assert status_after["verification_source"] == "self_declaration_h5"

    status_final = get_adult_verification_status(db, "wx_adult_test")
    assert status_final["adult_verified"] is True
