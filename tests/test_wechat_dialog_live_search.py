from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.product import Product
from app.models.user import User
from app.services import wechat_dialog_service as svc


def test_dialog_falls_back_to_live_search(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[Product.__table__, User.__table__])
    db = SessionLocal()

    monkeypatch.setattr(svc, "search_live_jd_products", lambda **kwargs: [
        {
            "source": "jd_live",
            "jd_sku_id": "1001",
            "title": "维达卷纸超值装",
            "short_url": "https://u.jd.com/mock-paper-1",
            "product_url": "https://u.jd.com/mock-paper-1",
            "category_name": "卷纸",
            "shop_name": "维达官方旗舰店",
            "price": 49.9,
            "coupon_price": 39.9,
            "commission_rate": 12.0,
            "estimated_commission": 4.0,
            "sales_volume": 500,
            "merchant_health_score": 0,
            "merchant_recommendable": True,
            "reason": "当前券后更便宜，到手价更有优势",
            "compliance_level": "normal",
        },
        {
            "source": "jd_live",
            "jd_sku_id": "1002",
            "title": "清风卷纸家庭装",
            "short_url": "https://u.jd.com/mock-paper-2",
            "product_url": "https://u.jd.com/mock-paper-2",
            "category_name": "卷纸",
            "shop_name": "清风旗舰店",
            "price": 59.9,
            "coupon_price": 45.9,
            "commission_rate": 10.0,
            "estimated_commission": 4.0,
            "sales_volume": 800,
            "merchant_health_score": 0,
            "merchant_recommendable": True,
            "reason": "已有800人下单，热度更高",
            "compliance_level": "normal",
        },
        {
            "source": "jd_live",
            "jd_sku_id": "1003",
            "title": "心相印卷纸实惠装",
            "short_url": "https://u.jd.com/mock-paper-3",
            "product_url": "https://u.jd.com/mock-paper-3",
            "category_name": "卷纸",
            "shop_name": "心相印旗舰店",
            "price": 42.9,
            "coupon_price": 36.9,
            "commission_rate": 9.0,
            "estimated_commission": 3.0,
            "sales_volume": 300,
            "merchant_health_score": 0,
            "merchant_recommendable": True,
            "reason": "价格比较合适，适合直接看看",
            "compliance_level": "normal",
        },
    ])

    reply = svc.get_recommendation_reply(db, "wx_live_user", "我想买卫生纸")
    assert "实时检索" in reply
    assert "查看链接：" in reply
    assert "清风卷纸家庭装" in reply
    assert "维达卷纸超值装" in reply
    assert "心相印卷纸实惠装" in reply
