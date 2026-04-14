import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.user import User
from app.services.user_profile_service import update_user_profile_from_text


def test_update_user_profile_from_text():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[User.__table__])

    db = SessionLocal()
    user = update_user_profile_from_text(db, "wx_user_1", "我想买牙膏，要便宜点，而且最好京东自营")
    categories = json.loads(user.preferred_categories)

    assert user.interaction_count == 1
    assert user.last_query_text == "我想买牙膏，要便宜点，而且最好京东自营"
    assert categories["牙膏"] >= 2
    assert user.price_sensitive_score > 0
    assert user.self_operated_sensitive_score > 0
