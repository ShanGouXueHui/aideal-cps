from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.order import Order


def list_orders(db: Session, page: int = 1, page_size: int = 20):
    query = db.query(Order)

    total = query.count()
    items = (
        query.order_by(desc(Order.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "items": items,
    }
