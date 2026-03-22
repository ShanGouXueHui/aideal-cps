from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.user import User
from app.models.product import Product
from app.core.config import settings


def sync_mock_orders(db: Session):
    mock_orders = [
        {
            "jd_order_id": "JD202603220002",
            "sku_id": "1000002",
            "sku_name": "小米空气炸锅 6L 大容量",
            "order_amount": 249.00,
            "estimate_cos_price": 19.92,
            "actual_cos_price": 18.00,
            "subunionid": "u_1001",
        },
        {
            "jd_order_id": "JD202603220003",
            "sku_id": "1000003",
            "sku_name": "南极人 保暖内衣套装 男款秋冬加绒",
            "order_amount": 79.90,
            "estimate_cos_price": 9.59,
            "actual_cos_price": 8.50,
            "subunionid": "u_1001",
        },
    ]

    inserted = 0
    updated = 0

    for item in mock_orders:
        existing = db.query(Order).filter(Order.jd_order_id == item["jd_order_id"]).first()

        user = db.query(User).filter(User.subunionid == item["subunionid"]).first()
        product = db.query(Product).filter(Product.jd_sku_id == item["sku_id"]).first()

        order_data = {
            "jd_order_id": item["jd_order_id"],
            "user_id": user.id if user else None,
            "product_id": product.id if product else None,
            "subunionid": item["subunionid"],
            "site_id": settings.JD_SITE_ID,
            "position_id": settings.JD_POSITION_ID,
            "sku_id": item["sku_id"],
            "sku_name": item["sku_name"],
            "order_amount": item["order_amount"],
            "estimate_cos_price": item["estimate_cos_price"],
            "actual_cos_price": item["actual_cos_price"],
            "order_status": "paid",
        }

        if existing:
            for key, value in order_data.items():
                setattr(existing, key, value)
            updated += 1
        else:
            db.add(Order(**order_data))
            inserted += 1

    db.commit()

    return {
        "message": "mock orders synced successfully",
        "inserted": inserted,
        "updated": updated,
        "total": len(mock_orders),
    }
