from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.partner_account import PartnerAccount
from app.models.partner_point_redemption import PartnerPointRedemption
from app.models.partner_reward_ledger import PartnerRewardLedger
from app.models.partner_share_asset import PartnerShareAsset
from app.models.product import Product
from app.models.user import User
from app.services.partner_center_service import get_partner_center
from app.services.partner_redemption_service import commit_partner_redemption
from app.services.partner_reward_service import record_partner_reward_event
from app.services.partner_share_service import generate_partner_share_asset


class FakeJDClient:
    def promotion_bysubunionid_get(self, *, material_id, chain_type=3, scene_id=1, sub_union_id=None):
        return {
            "jd_union_open_promotion_bysubunionid_get_responce": {
                "getResult": {
                    "code": 200,
                    "data": {
                        "shortURL": "https://u.jd.com/fake-short-center",
                        "clickURL": "https://union-click.jd.com/fake-long-center"
                    },
                    "message": "success"
                }
            }
        }


def test_partner_center_aggregate():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            PartnerAccount.__table__,
            PartnerRewardLedger.__table__,
            PartnerPointRedemption.__table__,
            Product.__table__,
            PartnerShareAsset.__table__,
        ],
    )
    db = SessionLocal()

    product = Product(
        jd_sku_id="sku-center-1",
        title="中心测试商品",
        material_url="https://item.m.jd.com/product/100010793716.html",
        product_url="https://u.jd.com/origin-center",
        short_url="https://u.jd.com/origin-center",
        image_url="https://example.com/center.png",
        price=Decimal("99.90"),
        coupon_price=Decimal("59.90"),
        estimated_commission=Decimal("10.00"),
        commission_rate=20.0,
        sales_volume=88,
        elite_name="高佣榜",
        shop_name="中心测试店铺",
        status="active",
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    record_partner_reward_event(
        db,
        wechat_openid="wx_center_user",
        event_type="settled",
        commission_amount=1000,
        order_ref="center-set-001",
    )

    generate_partner_share_asset(
        db,
        wechat_openid="wx_center_user",
        product_id=product.id,
        jd_client=FakeJDClient(),
    )

    commit_partner_redemption(
        db,
        wechat_openid="wx_center_user",
        item_code="partner_activation_fee",
        use_points=100,
        note="center activation",
    )

    center = get_partner_center(db, wechat_openid="wx_center_user")

    assert center["profile"]["activation_fee_paid"] is True
    assert center["reward_overview"]["available_points"] == 300.0
    assert len(center["recent_assets"]) == 1
    assert len(center["recent_shareable_products"]) >= 1
    assert len(center["redemption_history"]["items"]) == 1
    assert center["monetization_closure"]["activation_required"] is False
