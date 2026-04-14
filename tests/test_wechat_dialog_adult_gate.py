from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.product import Product
from app.models.user import User
from app.services.wechat_dialog_service import get_recommendation_reply


def _make_product(jd_sku_id: str, title: str, compliance_level: str, age_gate_required: bool):
    return Product(
        jd_sku_id=jd_sku_id,
        title=title,
        image_url="https://example.com/a.png",
        product_url="https://u.jd.com/a",
        material_url="https://item.m.jd.com/product/1.html",
        short_url="https://u.jd.com/a",
        category_name="成人用品",
        shop_name="测试店铺",
        price=Decimal("10.00"),
        coupon_price=Decimal("9.00"),
        commission_rate=10.0,
        estimated_commission=Decimal("1.00"),
        sales_volume=10,
        merchant_health_score=80.0,
        merchant_recommendable=True,
        compliance_level=compliance_level,
        age_gate_required=age_gate_required,
        allow_proactive_push=(compliance_level == "normal"),
        allow_partner_share=(compliance_level == "normal"),
        status="active",
    )


def test_wechat_dialog_returns_adult_gate_for_minor_user():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__, User.__table__])
    db = SessionLocal()

    db.add(_make_product("r1", "成人情趣跳蛋", "restricted", True))
    db.commit()

    reply = get_recommendation_reply(db, "wx_minor_user", "我想买跳蛋")
    assert "成年声明" in reply
    assert "/h5/adult-verify?wechat_openid=wx_minor_user" in reply


def test_wechat_dialog_allows_passive_view_for_adult_verified_user():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__, User.__table__])
    db = SessionLocal()

    db.add(_make_product("r1", "成人情趣跳蛋", "restricted", True))
    db.add(
        User(
            wechat_openid="wx_adult_user",
            subunionid="subu_test_adult",
            adult_verified=True,
            verification_source="self_declaration_h5",
        )
    )
    db.commit()

    reply = get_recommendation_reply(db, "wx_adult_user", "我想买跳蛋")
    assert "查看链接：" in reply
    assert "成年声明" not in reply
