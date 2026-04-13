from typing import Optional

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.models.product import Product


def get_products(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    category_name: Optional[str] = None,
    elite_id: Optional[int] = None,
    elite_name: Optional[str] = None,
    shop_name: Optional[str] = None,
    min_commission_rate: Optional[float] = None,
    has_short_url: Optional[bool] = None,
    order_by: str = "sales_volume",
    sort: str = "desc",
):
    query = db.query(Product).filter(Product.status == "active")

    if keyword:
        query = query.filter(Product.title.ilike(f"%{keyword}%"))
    if category_name:
        query = query.filter(Product.category_name == category_name)
    if elite_id is not None:
        query = query.filter(Product.elite_id == elite_id)
    if elite_name:
        query = query.filter(Product.elite_name == elite_name)
    if shop_name:
        query = query.filter(Product.shop_name.ilike(f"%{shop_name}%"))
    if min_commission_rate is not None:
        query = query.filter(Product.commission_rate >= min_commission_rate)
    if has_short_url is True:
        query = query.filter(Product.short_url.isnot(None), Product.short_url != "")
    elif has_short_url is False:
        query = query.filter((Product.short_url.is_(None)) | (Product.short_url == ""))

    order_field_map = {
        "sales_volume": Product.sales_volume,
        "commission_rate": Product.commission_rate,
        "updated_at": Product.updated_at,
        "price": Product.price,
        "coupon_price": Product.coupon_price,
    }
    order_field = order_field_map.get(order_by, Product.sales_volume)
    order_func = asc if sort == "asc" else desc

    total = query.count()
    items = (
        query.order_by(order_func(order_field), desc(Product.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "items": items}


def get_product_by_id(db: Session, product_id: int):
    return (
        db.query(Product)
        .filter(Product.id == product_id, Product.status == "active")
        .first()
    )
