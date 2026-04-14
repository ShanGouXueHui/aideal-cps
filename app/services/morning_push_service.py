from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import asc, case, desc
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.user import User
from app.services.user_profile_config_service import load_morning_push_copy
from app.services.user_profile_service import preferred_category

BASE_URL = "http://8.136.28.6"


def _safe_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _priority_mode(user: User) -> str:
    scores = {
        "price": float(user.price_sensitive_score or 0),
        "quality": float(user.quality_sensitive_score or 0),
        "sales": float(user.sales_sensitive_score or 0),
        "self_operated": float(user.self_operated_sensitive_score or 0),
    }
    mode, value = max(scores.items(), key=lambda kv: kv[1])
    return mode if value > 0 else "fallback"


def _base_query(db: Session):
    return (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.merchant_recommendable.is_(True),
            Product.short_url.isnot(None),
            Product.short_url != "",
        )
    )


def _ordered_query(query, mode: str):
    if mode == "price":
        return query.order_by(
            asc(Product.coupon_price),
            desc(Product.merchant_health_score),
            desc(Product.sales_volume),
            desc(Product.updated_at),
        )
    if mode == "quality":
        return query.order_by(
            desc(Product.merchant_health_score),
            desc(Product.sales_volume),
            asc(Product.coupon_price),
            desc(Product.updated_at),
        )
    if mode == "sales":
        return query.order_by(
            desc(Product.sales_volume),
            desc(Product.merchant_health_score),
            asc(Product.coupon_price),
            desc(Product.updated_at),
        )
    if mode == "self_operated":
        return query.order_by(
            desc(case((Product.owner == "g", 1), else_=0)),
            desc(Product.merchant_health_score),
            desc(Product.sales_volume),
            asc(Product.coupon_price),
            desc(Product.updated_at),
        )
    return query.order_by(
        desc(Product.merchant_health_score),
        desc(Product.sales_volume),
        asc(Product.coupon_price),
        desc(Product.updated_at),
    )


def select_morning_product(db: Session, user: User) -> tuple[Product | None, str | None, str]:
    mode = _priority_mode(user)
    category = preferred_category(user)

    query = _base_query(db)
    if category:
        query = query.filter(Product.category_name.ilike(f"%{category}%"))
    product = _ordered_query(query, mode).first()

    if not product and category:
        product = _ordered_query(_base_query(db), mode).first()

    return product, category, mode


def build_morning_push_message(user: User, product: Product, *, category: str | None, mode: str) -> str:
    copy = load_morning_push_copy()
    intro_map = {
        "price": copy["price_intro"],
        "quality": copy["quality_intro"],
        "sales": copy["sales_intro"],
        "self_operated": copy["self_operated_intro"],
        "fallback": copy["fallback_intro"],
    }
    intro = intro_map.get(mode, copy["fallback_intro"])
    coupon_price = _safe_decimal(getattr(product, "coupon_price", 0) or 0)
    price = _safe_decimal(getattr(product, "price", 0) or 0)
    display_price = coupon_price if coupon_price > 0 else price
    category_text = f"偏好品类：{category}\n" if category else ""
    link = f"{BASE_URL}/api/promotion/redirect?wechat_openid={user.wechat_openid}&product_id={product.id}&scene=morning_push&slot=1"

    return (
        f"{intro}\n\n"
        f"{category_text}"
        f"{product.title}\n"
        f"到手参考：¥{display_price:.2f}\n"
        f"店铺：{product.shop_name or '店铺信息待补充'}\n"
        f"查看链接：{link}\n\n"
        f"{copy['tail_hint']}"
    )


def generate_morning_push_candidates(db: Session, *, current_hour: int = 8, limit: int = 20) -> list[dict]:
    now = datetime.now(timezone.utc)
    users = (
        db.query(User)
        .filter(
            User.morning_push_enabled.is_(True),
            User.morning_push_hour == current_hour,
            User.last_interaction_at.isnot(None),
        )
        .order_by(User.last_interaction_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for user in users:
        if user.last_push_at and user.last_push_at.date() == now.date():
            continue

        product, category, mode = select_morning_product(db, user)
        if not product:
            continue

        results.append(
            {
                "user_id": user.id,
                "wechat_openid": user.wechat_openid,
                "product_id": product.id,
                "priority_mode": mode,
                "preferred_category": category,
                "message": build_morning_push_message(user, product, category=category, mode=mode),
            }
        )
    return results
