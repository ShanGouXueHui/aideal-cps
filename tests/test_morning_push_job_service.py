import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.product import Product
from app.models.user import User
from app.services.morning_push_job_service import build_morning_push_job


def test_build_morning_push_job(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[User.__table__, Product.__table__])
    db = SessionLocal()

    user = User(
        wechat_openid="wx_job_1",
        subunionid="wx_sub_job_1",
        preferred_categories=json.dumps({"牙膏": 3}, ensure_ascii=False),
        price_sensitive_score=5,
        morning_push_enabled=True,
        morning_push_hour=8,
        last_interaction_at=datetime.now(timezone.utc),
    )
    product = Product(
        jd_sku_id="sku-job",
        title="牙膏晨推商品",
        category_name="牙膏",
        shop_name="店铺A",
        short_url="https://u.jd.com/a",
        product_url="https://u.jd.com/a",
        price=Decimal("39.9"),
        coupon_price=Decimal("19.9"),
        sales_volume=100,
        commission_rate=10,
        merchant_health_score=80,
        merchant_recommendable=True,
        status="active",
    )
    db.add_all([user, product])
    db.commit()

    result = build_morning_push_job(db, current_hour=8, limit=10, output_root=str(tmp_path), mark_sent=False)
    assert result["count"] == 1
    assert Path(result["job_file"]).exists()
    assert Path(result["rows"][0]["poster_path"]).exists()
