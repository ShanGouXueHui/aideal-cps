from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.click_log import ClickLog
from app.models.merchant_profile import MerchantProfile
from app.models.partner_account import PartnerAccount
from app.models.partner_share_asset import PartnerShareAsset
from app.models.partner_share_click import PartnerShareClick
from app.models.product import Product
from app.services.catalog_refresh_service import (
    inactivate_expired_products,
    purge_stale_products,
    refresh_keyword_catalog,
)


class FakeJDClient:
    def goods_query(self, **kwargs):
        return {
            "jd_union_open_goods_query_responce": {
                "queryResult": {
                    "code": 200,
                    "data": [
                        {
                            "skuId": 1001,
                            "skuName": "苏菲夜用卫生巾超熟睡组合",
                            "materialUrl": "https://item.m.jd.com/product/1001.html",
                            "priceInfo": {"price": 59.9, "lowestCouponPrice": 39.9},
                            "commissionInfo": {"commissionShare": 20, "commission": 8},
                            "categoryInfo": {"cid3Name": "卫生巾"},
                            "shopInfo": {"shopName": "苏菲官方旗舰店", "shopId": 11},
                            "inOrderCount30DaysSku": 888,
                            "forbidTypes": [0]
                        },
                        {
                            "skuId": 1002,
                            "skuName": "清风抽纸家庭装",
                            "materialUrl": "https://item.m.jd.com/product/1002.html",
                            "priceInfo": {"price": 29.9, "lowestCouponPrice": 24.9},
                            "commissionInfo": {"commissionShare": 10, "commission": 2},
                            "categoryInfo": {"cid3Name": "抽纸"},
                            "shopInfo": {"shopName": "清风旗舰店", "shopId": 22},
                            "inOrderCount30DaysSku": 666,
                            "forbidTypes": [0]
                        }
                    ]
                }
            }
        }

    def promotion_bysubunionid_get(self, **kwargs):
        material_id = kwargs["material_id"]
        return {
            "jd_union_open_promotion_bysubunionid_get_responce": {
                "getResult": {
                    "code": 200,
                    "data": {"shortURL": f"https://u.jd.com/mock?to={material_id}"}
                }
            }
        }


def test_refresh_keyword_catalog_upserts_products():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Product.__table__,
            MerchantProfile.__table__,
            ClickLog.__table__,
            PartnerAccount.__table__,
            PartnerShareAsset.__table__,
            PartnerShareClick.__table__,
        ],
    )
    db = SessionLocal()

    result = refresh_keyword_catalog(
        db,
        keyword="卫生巾",
        limit=5,
        jd_client=FakeJDClient(),
    )

    assert result["total"] == 2
    assert result["inserted"] == 2

    rows = db.query(Product).all()
    assert len(rows) == 2
    assert rows[0].status == "active"
    assert rows[0].last_sync_at is not None


def test_inactivate_and_purge_stale_products():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Product.__table__,
            MerchantProfile.__table__,
            ClickLog.__table__,
            PartnerAccount.__table__,
            PartnerShareAsset.__table__,
            PartnerShareClick.__table__,
        ],
    )
    db = SessionLocal()

    old_active = Product(
        jd_sku_id="old-active-1",
        title="旧商品A",
        price=Decimal("10.00"),
        coupon_price=Decimal("9.00"),
        commission_rate=1.0,
        estimated_commission=Decimal("1.00"),
        sales_volume=1,
        status="active",
        last_sync_at=datetime.now(timezone.utc) - timedelta(hours=100),
    )
    very_old_inactive = Product(
        jd_sku_id="old-inactive-1",
        title="旧商品B",
        price=Decimal("10.00"),
        coupon_price=Decimal("9.00"),
        commission_rate=1.0,
        estimated_commission=Decimal("1.00"),
        sales_volume=1,
        status="inactive",
        last_sync_at=datetime.now(timezone.utc) - timedelta(hours=300),
    )
    fresh_active = Product(
        jd_sku_id="fresh-1",
        title="新商品",
        price=Decimal("10.00"),
        coupon_price=Decimal("9.00"),
        commission_rate=1.0,
        estimated_commission=Decimal("1.00"),
        sales_volume=1,
        status="active",
        last_sync_at=datetime.now(timezone.utc),
    )

    db.add_all([old_active, very_old_inactive, fresh_active])
    db.commit()

    inactive_result = inactivate_expired_products(db, expire_hours=72)
    purge_result = purge_stale_products(db, purge_hours=240)

    old_active_db = db.query(Product).filter(Product.jd_sku_id == "old-active-1").first()
    fresh_active_db = db.query(Product).filter(Product.jd_sku_id == "fresh-1").first()
    purged_db = db.query(Product).filter(Product.jd_sku_id == "old-inactive-1").first()

    assert inactive_result["inactive_count"] == 1
    assert purge_result["purged_count"] == 1
    assert old_active_db.status == "inactive"
    assert fresh_active_db.status == "active"
    assert purged_db is None
