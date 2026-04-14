from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.partner_account import PartnerAccount
from app.models.partner_share_asset import PartnerShareAsset
from app.models.partner_share_click import PartnerShareClick
from app.models.product import Product
from app.models.user import User
from app.services.partner_share_service import generate_partner_share_asset, open_partner_buy_link


class FakeJDClient:
    def promotion_bysubunionid_get(self, *, material_id, chain_type=3, scene_id=1, sub_union_id=None):
        return {
            "jd_union_open_promotion_bysubunionid_get_responce": {
                "getResult": {
                    "code": 200,
                    "data": {
                        "shortURL": "https://u.jd.com/fake-short",
                        "clickURL": "https://union-click.jd.com/fake-long",
                        "jShortCommand": "! TESTSHORT ! CA1234",
                        "jCommand": "测试长口令 TESTLONG"
                    },
                    "message": "success"
                }
            }
        }


def test_generate_partner_asset_and_click():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            PartnerAccount.__table__,
            Product.__table__,
            PartnerShareAsset.__table__,
            PartnerShareClick.__table__,
        ],
    )
    db = SessionLocal()

    product = Product(
        jd_sku_id="sku-partner-1",
        title="测试合伙人商品",
        material_url="https://item.m.jd.com/product/100010793716.html",
        product_url="https://u.jd.com/origin",
        short_url="https://u.jd.com/origin",
        image_url="https://example.com/test.png",
        price=Decimal("59.90"),
        coupon_price=Decimal("39.90"),
        status="active",
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    asset = generate_partner_share_asset(
        db,
        wechat_openid="wx_partner_asset",
        product_id=product.id,
        jd_client=FakeJDClient(),
    )
    assert asset["buy_url"]
    assert asset["share_url"]
    assert asset["short_url"] == "https://u.jd.com/fake-short"
    assert asset["buy_qr_svg_path"]
    assert asset["share_qr_svg_path"]
    assert asset["poster_svg_path"]
    assert asset["buy_copy"]
    assert asset["share_copy"]
    assert asset["j_command_short"] == "! TESTSHORT ! CA1234"

    root = Path.cwd()
    assert (root / asset["buy_qr_svg_path"]).exists()
    assert (root / asset["share_qr_svg_path"]).exists()
    assert (root / asset["poster_svg_path"]).exists()

    click = open_partner_buy_link(
        db,
        asset_token=asset["asset_token"],
        request_source="pytest",
        client_ip="127.0.0.1",
        user_agent="pytest-agent",
        referer=None,
    )
    assert click["redirect_url"] == "https://u.jd.com/fake-short"
