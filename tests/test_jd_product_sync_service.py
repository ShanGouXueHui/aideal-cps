from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.product import Product
from app.services.jd_product_sync_service import normalize_jd_item, upsert_product


def test_normalize_jd_item():
    item = {
        "skuName": "测试商品",
        "skuId": 123,
        "materialUrl": "https://jingfen.jd.com/detail/abc.html",
        "priceInfo": {"price": 99.9, "lowestCouponPrice": 79.9},
        "commissionInfo": {"commissionShare": 20, "commission": 15.5},
        "categoryInfo": {"cid3Name": "牙膏"},
        "shopInfo": {"shopName": "测试店", "shopId": 88},
        "resourceInfo": {"eliteId": 129, "eliteName": "高佣榜"},
        "imageInfo": {"whiteImage": "https://img.example/a.jpg"},
        "couponInfo": {"couponList": [{"quota": 100, "discount": 20}]},
        "inOrderCount30DaysSku": 1234,
        "owner": "p",
    }

    payload = normalize_jd_item(item, short_url="https://u.jd.com/test")
    assert payload["jd_sku_id"] == "123"
    assert payload["title"] == "测试商品"
    assert payload["short_url"] == "https://u.jd.com/test"
    assert payload["price"] == Decimal("99.9")
    assert payload["elite_id"] == 129
    assert payload["shop_name"] == "测试店"


def test_upsert_product_insert_then_update():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__])

    db = SessionLocal()

    payload = {
        "jd_sku_id": "sku-1",
        "title": "商品1",
        "description": None,
        "image_url": None,
        "product_url": "https://u.jd.com/1",
        "material_url": "https://jingfen.jd.com/detail/1.html",
        "short_url": "https://u.jd.com/1",
        "category_name": "分类",
        "shop_name": "店铺",
        "shop_id": "1",
        "price": Decimal("10.0"),
        "coupon_price": Decimal("9.0"),
        "commission_rate": 20.0,
        "estimated_commission": Decimal("2.0"),
        "sales_volume": 100,
        "coupon_info": "满100减10",
        "ai_reason": None,
        "ai_tags": "高佣榜",
        "elite_id": 129,
        "elite_name": "高佣榜",
        "owner": "p",
        "status": "active",
        "last_sync_at": None,
    }

    _, action1 = upsert_product(db, payload)
    db.commit()
    assert action1 == "inserted"

    payload["title"] = "商品1-更新"
    _, action2 = upsert_product(db, payload)
    db.commit()
    assert action2 == "updated"

    row = db.query(Product).filter(Product.jd_sku_id == "sku-1").first()
    assert row.title == "商品1-更新"
