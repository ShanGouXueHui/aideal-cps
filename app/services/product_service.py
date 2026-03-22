from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.product import Product


def get_products(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    category_name: Optional[str] = None,
):
    query = db.query(Product).filter(Product.status == "active")

    if keyword:
        query = query.filter(Product.title.ilike(f"%{keyword}%"))

    if category_name:
        query = query.filter(Product.category_name == category_name)

    total = query.count()

    items = (
        query.order_by(desc(Product.sales_volume), desc(Product.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "items": items
    }


def get_product_by_id(db: Session, product_id: int):
    return (
        db.query(Product)
        .filter(Product.id == product_id, Product.status == "active")
        .first()
    )
