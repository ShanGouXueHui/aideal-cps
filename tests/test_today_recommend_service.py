from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.product import Product
from app.services.today_recommend_service import get_today_recommend_reply


def test_today_recommend_reply_uses_real_products():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__])
    db = SessionLocal()

    rows = [
        Product(
            jd_sku_id="sku1",
            title="维达卷纸超值装",
            short_url="https://u.jd.com/mock1",
            product_url="https://u.jd.com/mock1",
            shop_name="维达旗舰店",
            price=Decimal("59.90"),
            coupon_price=Decimal("39.90"),
            sales_volume=500,
            estimated_commission=Decimal("4.00"),
            status="active",
            compliance_level="normal",
            allow_proactive_push=True,
            allow_partner_share=True,
            merchant_recommendable=True,
        ),
        Product(
            jd_sku_id="sku2",
            title="清风卷纸家庭装",
            short_url="https://u.jd.com/mock2",
            product_url="https://u.jd.com/mock2",
            shop_name="清风旗舰店",
            price=Decimal("69.90"),
            coupon_price=Decimal("49.90"),
            sales_volume=300,
            estimated_commission=Decimal("3.00"),
            status="active",
            compliance_level="normal",
            allow_proactive_push=True,
            allow_partner_share=True,
            merchant_recommendable=True,
        ),
        Product(
            jd_sku_id="sku3",
            title="测试不合规商品",
            short_url="https://u.jd.com/mock3",
            product_url="https://u.jd.com/mock3",
            shop_name="测试店铺",
            price=Decimal("29.90"),
            coupon_price=Decimal("19.90"),
            sales_volume=999,
            estimated_commission=Decimal("9.00"),
            status="active",
            compliance_level="restricted",
            allow_proactive_push=True,
            allow_partner_share=True,
            merchant_recommendable=True,
        ),
    ]
    db.add_all(rows)
    db.commit()

    reply = get_today_recommend_reply(db, "wx_test_user")
    assert "维达卷纸超值装" in reply
    assert "清风卷纸家庭装" in reply
    assert "测试不合规商品" not in reply
    assert "menu_today_recommend" in reply


def test_today_recommend_reply_handles_empty_pool():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__])
    db = SessionLocal()

    reply = get_today_recommend_reply(db, "wx_test_user")
    assert "当前商品池里还没有足够适合主动推荐的结果" in reply
