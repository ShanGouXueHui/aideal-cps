import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.product import Product
from app.models.user import User
from app.services.morning_push_service import generate_morning_push_candidates


def test_generate_morning_push_candidates_prefers_user_category_and_price():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[User.__table__, Product.__table__])

    db = SessionLocal()
    user = User(
        wechat_openid="wx_push_1",
        subunionid="wx_sub_push_1",
        preferred_categories=json.dumps({"牙膏": 3}, ensure_ascii=False),
        price_sensitive_score=5,
        morning_push_enabled=True,
        morning_push_hour=8,
        last_interaction_at=datetime.now(timezone.utc),
    )
    p1 = Product(
        jd_sku_id="sku-a",
        title="牙膏A",
        category_name="牙膏",
        shop_name="店铺A",
        short_url="https://u.jd.com/a",
        product_url="https://u.jd.com/a",
        price=Decimal("50"),
        coupon_price=Decimal("19.9"),
        sales_volume=50,
        commission_rate=5,
        merchant_health_score=80,
        merchant_recommendable=True,
        status="active",
    )
    p2 = Product(
        jd_sku_id="sku-b",
        title="牙膏B",
        category_name="牙膏",
        shop_name="店铺B",
        short_url="https://u.jd.com/b",
        product_url="https://u.jd.com/b",
        price=Decimal("50"),
        coupon_price=Decimal("29.9"),
        sales_volume=100,
        commission_rate=5,
        merchant_health_score=85,
        merchant_recommendable=True,
        status="active",
    )
    db.add_all([user, p1, p2])
    db.commit()

    rows = generate_morning_push_candidates(db, current_hour=8, limit=10)
    assert len(rows) == 1
    assert rows[0]["product_id"] == p1.id
    assert rows[0]["preferred_category"] == "牙膏"
    assert rows[0]["priority_mode"] == "price"
