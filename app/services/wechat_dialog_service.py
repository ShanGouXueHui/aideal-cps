from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.user import User
from app.services.adult_verification_service import build_adult_verification_url
from app.services.product_compliance_service import apply_product_visibility_filter
from app.services.product_intent_service import parse_product_intent
from app.services.recommendation_service import generate_reason
from app.services.wechat_copy_service import get_copy


BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://8.136.28.6")


def _safe_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _short_title(title: str, max_len: int = 24) -> str:
    title = (title or "").strip()
    if len(title) <= max_len:
        return title
    return title[: max_len - 1] + "…"


def _discount_amount(product: Product) -> Decimal:
    price = _safe_decimal(getattr(product, "price", 0))
    coupon_price = _safe_decimal(getattr(product, "coupon_price", 0))
    discount = price - coupon_price
    if discount < 0:
        return Decimal("0")
    return discount


def _token_match_count(product: Product, tokens: list[str]) -> int:
    haystack = " ".join(
        [
            str(getattr(product, "title", "") or ""),
            str(getattr(product, "category_name", "") or ""),
            str(getattr(product, "shop_name", "") or ""),
        ]
    ).lower()
    count = 0
    for token in tokens:
        if token.lower() in haystack:
            count += 1
    return count


def _preference_score(product: Product, intent: dict[str, Any]) -> Decimal:
    token_hits = Decimal(_token_match_count(product, intent.get("search_tokens", [])))
    sales_volume = _safe_decimal(getattr(product, "sales_volume", 0) or 0)
    commission_rate = _safe_decimal(getattr(product, "commission_rate", 0) or 0)
    merchant_health = _safe_decimal(getattr(product, "merchant_health_score", 0) or 0)
    coupon_price = _safe_decimal(getattr(product, "coupon_price", 0) or 0)
    discount = _discount_amount(product)

    score = token_hits * Decimal("40")
    score += merchant_health * Decimal("0.5")
    score += sales_volume * Decimal("0.03")
    score += commission_rate * Decimal("0.05")
    score += discount * Decimal("0.15")

    if intent.get("wants_low_price"):
        score += discount * Decimal("0.8")
        score -= coupon_price * Decimal("0.06")
    if intent.get("wants_quality"):
        score += merchant_health * Decimal("0.8")
    if intent.get("wants_sales"):
        score += sales_volume * Decimal("0.08")
    if intent.get("wants_self_operated") and str(getattr(product, "owner", "") or "") == "g":
        score += Decimal("12")
    return score


def _resolve_adult_verified(db: Session, openid: str) -> bool:
    user = db.query(User).filter(User.wechat_openid == openid).first()
    return bool(getattr(user, "adult_verified", False)) if user else False


def _restricted_candidates_exist(db: Session, intent: dict[str, Any]) -> bool:
    query = (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.merchant_recommendable.is_(True),
            Product.short_url.isnot(None),
            Product.short_url != "",
            Product.compliance_level == "restricted",
        )
    )

    tokens = intent.get("search_tokens", [])
    if tokens:
        clauses = []
        for token in tokens[:6]:
            like = f"%{token}%"
            clauses.extend(
                [
                    Product.title.ilike(like),
                    Product.category_name.ilike(like),
                    Product.shop_name.ilike(like),
                ]
            )
        query = query.filter(or_(*clauses))

    return query.first() is not None


def search_candidate_products(
    db: Session,
    intent: dict[str, Any],
    adult_verified: bool = False,
    limit: int = 60,
) -> list[Product]:
    query = (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.merchant_recommendable.is_(True),
            Product.short_url.isnot(None),
            Product.short_url != "",
        )
    )
    query = apply_product_visibility_filter(query, adult_verified=adult_verified)

    tokens = intent.get("search_tokens", [])
    if tokens:
        clauses = []
        for token in tokens[:6]:
            like = f"%{token}%"
            clauses.extend(
                [
                    Product.title.ilike(like),
                    Product.category_name.ilike(like),
                    Product.shop_name.ilike(like),
                ]
            )
        query = query.filter(or_(*clauses))

    return (
        query.order_by(
            desc(Product.merchant_health_score),
            desc(Product.sales_volume),
            desc(Product.updated_at),
        )
        .limit(limit)
        .all()
    )


def select_three_products(products: list[Product], intent: dict[str, Any]) -> list[tuple[str, Product]]:
    if not products:
        return []

    remaining = list(products)
    selected: list[tuple[str, Product]] = []

    best_fit = max(remaining, key=lambda p: _preference_score(p, intent))
    selected.append(("最符合你需求", best_fit))
    remaining = [p for p in remaining if p.id != best_fit.id]

    if remaining:
        best_sales = max(
            remaining,
            key=lambda p: (
                _safe_decimal(getattr(p, "sales_volume", 0) or 0),
                _safe_decimal(getattr(p, "merchant_health_score", 0) or 0),
            ),
        )
        selected.append(("下单热度更高", best_sales))
        remaining = [p for p in remaining if p.id != best_sales.id]

    if remaining:
        safest = max(
            remaining,
            key=lambda p: (
                _safe_decimal(getattr(p, "merchant_health_score", 0) or 0),
                _safe_decimal(getattr(p, "commission_rate", 0) or 0),
            ),
        )
        selected.append(("口碑与店铺更稳", safest))

    return selected


def build_product_link(product: Product, openid: str, *, scene: str, slot: int) -> str:
    return f"{BASE_URL}/api/promotion/redirect?wechat_openid={openid}&product_id={product.id}&scene={scene}&slot={slot}"


def build_product_block(role_label: str, product: Product, openid: str, *, slot: int) -> str:
    reason = generate_reason(product)
    title = _short_title(getattr(product, "title", "优选商品"))
    coupon_price = _safe_decimal(getattr(product, "coupon_price", 0) or 0)
    price = _safe_decimal(getattr(product, "price", 0) or 0)
    display_price = coupon_price if coupon_price > 0 else price
    link = build_product_link(product, openid, scene="wechat_reply", slot=slot)
    shop_name = getattr(product, "shop_name", None) or "店铺信息待补充"
    return (
        f"{role_label}\n"
        f"{title}\n"
        f"到手参考：¥{display_price:.2f}\n"
        f"店铺：{shop_name}\n"
        f"理由：{reason}\n"
        f"查看链接：{link}"
    )


def build_recommendation_text(selected: list[tuple[str, Product]], openid: str, intent: dict[str, Any]) -> str:
    if not selected:
        return get_copy("no_result_text") + "\n\n" + get_copy("category_gap_text")

    if intent.get("wants_low_price"):
        intro = "我先偏向价格和到手价给你筛了一轮，再把高风险商品去掉，给你挑了 3 个更值得看的："
    elif intent.get("wants_quality"):
        intro = "我先偏向质量、口碑和店铺稳定性给你筛了一轮，再把高风险商品去掉，给你挑了 3 个更值得看的："
    else:
        intro = "我先按你的需求，从价格、口碑、店铺稳定性里筛了一轮，再把高风险商品去掉，给你挑了 3 个更值得看的："

    blocks = []
    for idx, (role_label, product) in enumerate(selected, start=1):
        blocks.append(f"{idx}.\n{build_product_block(role_label, product, openid, slot=idx)}")

    return f"{intro}\n\n" + "\n\n".join(blocks) + f"\n\n{get_copy('retry_hint_text')}"


def build_adult_gate_text(openid: str) -> str:
    verify_url = build_adult_verification_url(openid)
    return (
        "这类商品属于限制级内容，系统不会主动推荐。\n"
        "如你已年满18岁，可先完成成年声明，再继续被动查看：\n"
        f"{verify_url}\n\n"
        "完成后你可以重新发送商品名称，我再按规则帮你筛选。"
    )


def get_recommendation_reply(db: Session, openid: str, content: str) -> str:
    intent = parse_product_intent(content)
    if not intent["shopping_intent"]:
        return get_copy("non_shopping_redirect_text")

    adult_verified = _resolve_adult_verified(db, openid)
    candidates = search_candidate_products(db, intent, adult_verified=adult_verified, limit=60)

    if not candidates and not adult_verified and _restricted_candidates_exist(db, intent):
        return build_adult_gate_text(openid)

    if not candidates and intent.get("commodity"):
        fallback_intent = dict(intent)
        fallback_intent["search_tokens"] = [intent["commodity"]]
        candidates = search_candidate_products(db, fallback_intent, adult_verified=adult_verified, limit=60)
        intent = fallback_intent

    if not candidates and not adult_verified and _restricted_candidates_exist(db, intent):
        return build_adult_gate_text(openid)

    selected = select_three_products(candidates, intent)
    return build_recommendation_text(selected, openid, intent)


def get_help_reply() -> str:
    return get_copy("help_text")


def get_welcome_reply() -> str:
    return get_copy("welcome_text")
