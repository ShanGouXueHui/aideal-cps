from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.product import Product
from app.services import partner_share_entry_service as svc


def test_parse_share_product_keyword():
    assert svc.parse_share_product_keyword("分享商品 牙膏") == "牙膏"
    assert svc.parse_share_product_keyword("分享商品：洗衣液") == "洗衣液"
    assert svc.parse_share_product_keyword("分享商品") is None
    assert svc.parse_share_product_keyword("找商品 牙膏") is None


def test_get_partner_share_product_request_reply():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__])
    db = SessionLocal()

    product = Product(
        jd_sku_id="sku_share_1",
        title="维达卷纸超值装",
        short_url="https://u.jd.com/mock-share-1",
        product_url="https://u.jd.com/mock-share-1",
        category_name="卷纸",
        shop_name="维达旗舰店",
        price=Decimal("59.90"),
        coupon_price=Decimal("39.90"),
        sales_volume=500,
        estimated_commission=Decimal("4.00"),
        status="active",
        compliance_level="normal",
        allow_partner_share=True,
        merchant_recommendable=True,
    )
    db.add(product)
    db.commit()

    svc._generate_partner_asset_payload = lambda db, wechat_openid, product_id: {
        "buy_url": "http://8.136.28.6/api/partner/assets/demo/buy",
        "share_url": "http://8.136.28.6/api/partner/assets/demo/share",
        "reason": "当前券后更便宜，到手价更有优势。",
        "poster_svg_path": "data/demo/poster.svg",
        "buy_qr_svg_path": "data/demo/buy_qr.svg",
        "share_qr_svg_path": "data/demo/share_qr.svg",
        "partner_code": "pc_demo_001",
        "asset_token": "asset_demo_001",
        "buy_copy": "【智省优选】购买文案示例",
        "share_copy": "【智省优选合伙人推荐】分享文案示例",
        "title": "维达卷纸超值装",
    }

    reply = svc.get_partner_share_product_request_reply(db, "wx_share_user", "分享商品 卷纸")
    assert "维达卷纸超值装" in reply
    assert "自己先买：http://8.136.28.6/api/partner/assets/demo/buy" in reply
    assert "转发分享：http://8.136.28.6/api/partner/assets/demo/share" in reply
    assert "海报路径：data/demo/poster.svg" in reply
    assert "购买码路径：data/demo/buy_qr.svg" in reply
    assert "分享码路径：data/demo/share_qr.svg" in reply
    assert "购买文案：" in reply
    assert "分享文案：" in reply


def test_get_partner_share_product_request_reply_handles_empty():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__])
    db = SessionLocal()

    reply = svc.get_partner_share_product_request_reply(db, "wx_share_user", "分享商品 牙膏")
    assert "还没有找到适合直接分享的结果" in reply
