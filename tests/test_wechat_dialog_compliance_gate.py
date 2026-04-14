from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.product import Product
from app.services.wechat_dialog_service import search_candidate_products


def _make_product(jd_sku_id: str, title: str, compliance_level: str, age_gate_required: bool):
    return Product(
        jd_sku_id=jd_sku_id,
        title=title,
        image_url="https://example.com/a.png",
        product_url="https://u.jd.com/a",
        material_url="https://item.m.jd.com/product/1.html",
        short_url="https://u.jd.com/a",
        category_name="测试类目",
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


def test_wechat_dialog_filters_restricted_and_hard_block():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__])
    db = SessionLocal()

    db.add_all(
        [
            _make_product("n1", "普通洗衣液", "normal", False),
            _make_product("r1", "成人情趣用品", "restricted", True),
            _make_product("h1", "防狼喷雾剂", "hard_block", False),
        ]
    )
    db.commit()

    intent = {
        "search_tokens": [],
        "wants_low_price": False,
        "wants_quality": False,
        "wants_sales": False,
        "wants_self_operated": False,
    }

    minor_visible = search_candidate_products(db, intent, adult_verified=False, limit=20)
    adult_visible = search_candidate_products(db, intent, adult_verified=True, limit=20)

    minor_titles = {p.title for p in minor_visible}
    adult_titles = {p.title for p in adult_visible}

    assert "普通洗衣液" in minor_titles
    assert "成人情趣用品" not in minor_titles
    assert "防狼喷雾剂" not in minor_titles

    assert "普通洗衣液" in adult_titles
    assert "成人情趣用品" in adult_titles
    assert "防狼喷雾剂" not in adult_titles
