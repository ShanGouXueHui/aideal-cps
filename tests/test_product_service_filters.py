from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.product import Product
from app.services.product_service import get_products


def seed(db):
    rows = [
        Product(
            jd_sku_id="sku-1",
            title="高佣商品A",
            category_name="牙膏",
            shop_name="合和泰官方旗舰店",
            price=Decimal("139.6"),
            coupon_price=Decimal("79.6"),
            commission_rate=61.0,
            estimated_commission=Decimal("85.16"),
            sales_volume=200,
            elite_id=129,
            elite_name="高佣榜",
            short_url="https://u.jd.com/a",
            merchant_health_score=92.0,
            merchant_risk_flags=None,
            merchant_recommendable=True,
            status="active",
        ),
        Product(
            jd_sku_id="sku-2",
            title="普通商品B",
            category_name="水果罐头",
            shop_name="林家铺子旗舰店",
            price=Decimal("69.9"),
            coupon_price=Decimal("69.9"),
            commission_rate=2.5,
            estimated_commission=Decimal("1.75"),
            sales_volume=100,
            elite_id=129,
            elite_name="高佣榜",
            short_url="https://u.jd.com/b",
            merchant_health_score=78.0,
            merchant_risk_flags=None,
            merchant_recommendable=True,
            status="active",
        ),
        Product(
            jd_sku_id="sku-3",
            title="高风险商品C",
            category_name="防身用品",
            shop_name="风险店铺",
            price=Decimal("103.55"),
            coupon_price=Decimal("103.55"),
            commission_rate=30.0,
            estimated_commission=Decimal("31.07"),
            sales_volume=80,
            elite_id=31,
            elite_name="今日必推",
            short_url=None,
            merchant_health_score=55.0,
            merchant_risk_flags="poor_after_sales,price_too_high",
            merchant_recommendable=False,
            status="active",
        ),
    ]
    db.add_all(rows)
    db.commit()


def test_get_products_filter_by_elite_and_short_url():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__])
    db = SessionLocal()
    seed(db)

    result = get_products(
        db=db,
        elite_id=129,
        has_short_url=True,
        order_by="commission_rate",
        sort="desc",
    )

    assert result["total"] == 2
    assert result["items"][0].title == "高佣商品A"
    assert result["items"][1].title == "普通商品B"


def test_get_products_filter_by_shop_name_and_min_commission():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__])
    db = SessionLocal()
    seed(db)

    result = get_products(
        db=db,
        shop_name="风险店铺",
        min_commission_rate=20,
        merchant_recommendable_only=False,
    )

    assert result["total"] == 1
    assert result["items"][0].title == "高风险商品C"


def test_get_products_filter_by_merchant_fields():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__])
    db = SessionLocal()
    seed(db)

    result = get_products(
        db=db,
        merchant_recommendable_only=True,
        min_merchant_health_score=80,
        order_by="merchant_health_score",
        sort="desc",
    )

    assert result["total"] == 1
    assert result["items"][0].title == "高佣商品A"
