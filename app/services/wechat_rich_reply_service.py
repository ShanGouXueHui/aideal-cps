from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.recommendation_guard_service import allow_proactive_recommend
from app.services.wechat_service import build_news_response


BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")


def _safe_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _short_title(title: str, max_len: int = 30) -> str:
    title = (title or "").strip()
    if len(title) <= max_len:
        return title
    return title[: max_len - 1] + "…"


def _get_attr(item: Any, *names: str) -> str:
    for name in names:
        value = getattr(item, name, None)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _pick_click_url(product: Product, wechat_openid: str, *, scene: str, slot: int) -> str:
    short_url = _get_attr(product, "short_url")
    if short_url:
        return short_url

    product_url = _get_attr(product, "product_url")
    if product_url:
        return product_url

    material_url = _get_attr(product, "material_url")
    if material_url:
        return material_url

    if BASE_URL and getattr(product, "id", None):
        return (
            f"{BASE_URL}/api/promotion/redirect"
            f"?wechat_openid={wechat_openid}"
            f"&product_id={int(product.id)}"
            f"&scene={scene}"
            f"&slot={slot}"
        )

    return ""


def _pick_image_url(product: Product) -> str:
    return _get_attr(
        product,
        "poster_image_url",
        "poster_url",
        "image_url",
        "img_url",
        "pic_url",
    )


def _build_reason_line(product: Product) -> str:
    parts: list[str] = []

    price = _safe_decimal(getattr(product, "price", 0))
    coupon_price = _safe_decimal(getattr(product, "coupon_price", 0))
    sales_volume = _safe_int(getattr(product, "sales_volume", 0))
    owner = (_get_attr(product, "owner") or "").lower()
    shop_name = _get_attr(product, "shop_name")

    if coupon_price > 0 and price > coupon_price:
        diff = price - coupon_price
        parts.append(f"券后比标价省{diff:.2f}元")
        parts.append(f"到手参考¥{coupon_price:.2f}")
    elif coupon_price > 0:
        parts.append(f"到手参考¥{coupon_price:.2f}")
    elif price > 0:
        parts.append(f"参考价¥{price:.2f}")

    if sales_volume > 0:
        parts.append(f"已售{sales_volume}件")

    if owner == "g":
        parts.append("京东自营")
    elif shop_name:
        parts.append(shop_name)

    if not parts:
        return "当前商品池里综合条件更稳，点开可直接看京东详情"

    text = "｜".join(parts[:3])
    return text[:120]


def _today_recommend_query(db: Session):
    rows = (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.compliance_level == "normal",
            Product.allow_proactive_push.is_(True),
            Product.merchant_recommendable.is_(True),
            Product.short_url.isnot(None),
            Product.short_url != "",
            Product.image_url.isnot(None),
            Product.image_url != "",
        )
        .all()
    )
    rows = [row for row in rows if allow_proactive_recommend(row)]
    rows.sort(
        key=lambda row: (
            _safe_int(getattr(row, "sales_volume", 0)),
            float(_safe_decimal(getattr(row, "estimated_commission", 0))),
            int(getattr(row, "id", 0) or 0),
        ),
        reverse=True,
    )
    return rows


def _find_product_entry_query(db: Session):
    rows = (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.compliance_level == "normal",
            Product.merchant_recommendable.is_(True),
            Product.short_url.isnot(None),
            Product.short_url != "",
            Product.image_url.isnot(None),
            Product.image_url != "",
        )
        .all()
    )
    rows.sort(
        key=lambda row: (
            _safe_int(getattr(row, "sales_volume", 0)),
            float(_safe_decimal(getattr(row, "merchant_health_score", 0))),
            float(_safe_decimal(getattr(row, "estimated_commission", 0))),
            int(getattr(row, "id", 0) or 0),
        ),
        reverse=True,
    )
    return rows


def _build_article(product: Product, wechat_openid: str, *, scene: str, slot: int, title_prefix: str = "", suffix_hint: str = "") -> dict:
    title = _short_title(_get_attr(product, "title") or "智省优选推荐")
    if title_prefix:
        title = f"{title_prefix}{title}"

    description = _build_reason_line(product)
    if suffix_hint:
        description = f"{description}；{suffix_hint}"

    return {
        "title": title[:64],
        "description": description[:120],
        "pic_url": _pick_image_url(product),
        "url": _pick_click_url(product, wechat_openid, scene=scene, slot=slot),
    }


def get_today_recommend_news_response(db: Session, wechat_openid: str, *, to_user: str, from_user: str) -> str | None:
    products = _today_recommend_query(db)[:3]
    if not products:
        return None

    articles = []
    for idx, product in enumerate(products, start=1):
        articles.append(
            _build_article(
                product,
                wechat_openid,
                scene="menu_today_recommend",
                slot=idx,
                title_prefix=f"今日推荐{idx}｜",
                suffix_hint="点图直达京东",
            )
        )

    return build_news_response(to_user, from_user, articles)


def get_find_product_entry_news_response(db: Session, wechat_openid: str, *, to_user: str, from_user: str) -> str | None:
    products = _find_product_entry_query(db)
    if not products:
        return None

    hero = products[0]
    article = _build_article(
        hero,
        wechat_openid,
        scene="menu_find_product",
        slot=1,
        title_prefix="点图直达｜",
        suffix_hint="也可直接回复：卫生纸 / 洗衣液 / 宝宝湿巾 / 京东自营",
    )
    return build_news_response(to_user, from_user, [article])
