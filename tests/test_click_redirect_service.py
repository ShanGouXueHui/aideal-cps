from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.click_log import ClickLog
from app.models.product import Product
from app.models.user import User
from app.services.click_redirect_service import create_click_redirect


def test_create_click_redirect_uses_existing_short_url():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[User.__table__, Product.__table__, ClickLog.__table__])
    db = SessionLocal()

    user = User(wechat_openid="wx_openid_1", subunionid="wx_sub_1", nickname="u1")
    product = Product(
        jd_sku_id="sku-1",
        title="测试商品",
        product_url="https://u.jd.com/abc",
        short_url="https://u.jd.com/abc",
        material_url="https://jingfen.jd.com/detail/abc.html",
        price=Decimal("10"),
        coupon_price=Decimal("9"),
        commission_rate=10,
        estimated_commission=Decimal("1"),
        sales_volume=1,
        status="active",
    )
    db.add(user)
    db.add(product)
    db.commit()
    db.refresh(product)

    result = create_click_redirect(
        db,
        wechat_openid="wx_openid_1",
        product_id=product.id,
        scene="wechat_reply",
        slot=1,
        request_source="wechat_redirect",
        client_ip="127.0.0.1",
        user_agent="pytest-agent",
        referer="https://example.com",
    )

    assert result["final_url"] == "https://u.jd.com/abc"
    row = db.query(ClickLog).first()
    assert row.trace_id is not None
    assert row.scene == "wechat_reply"
    assert row.slot == 1
    assert row.final_url == "https://u.jd.com/abc"
