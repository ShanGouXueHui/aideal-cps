from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.user import User
from app.services.adult_verification_service import build_adult_verification_url
from app.services.jd_live_search_service import search_live_jd_products
from app.services.live_search_config_service import load_live_search_rules
from app.services.product_compliance_service import apply_product_visibility_filter
from app.services.product_intent_service import parse_product_intent
from app.services.recommendation_service import generate_reason
from app.services.wechat_copy_service import get_copy


def _public_base_url() -> str:
    env_url = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if env_url:
        return env_url
    try:
        from app.core.wechat_recommend_config import PUBLIC_BASE_URL

        if PUBLIC_BASE_URL:
            return str(PUBLIC_BASE_URL).rstrip("/")
    except Exception:
        pass
    return "https://aidealfy.cn"


BASE_URL = _public_base_url()


def _safe_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _short_title(title: str, max_len: int = 24) -> str:
    title = (title or "").strip()
    if len(title) <= max_len:
        return title
    return title[: max_len - 1] + "…"


def _get_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _discount_amount(item: Any) -> Decimal:
    price = _safe_decimal(_get_value(item, "price", 0))
    coupon_price = _safe_decimal(_get_value(item, "coupon_price", 0))
    discount = price - coupon_price
    if discount < 0:
        return Decimal("0")
    return discount


def _token_match_count(item: Any, tokens: list[str]) -> int:
    haystack = " ".join(
        [
            str(_get_value(item, "title", "") or ""),
            str(_get_value(item, "category_name", "") or ""),
            str(_get_value(item, "shop_name", "") or ""),
        ]
    ).lower()
    count = 0
    for token in tokens:
        if token.lower() in haystack:
            count += 1
    return count


def _item_haystack(item: Any) -> str:
    return " ".join(
        [
            str(_get_value(item, "title", "") or ""),
            str(_get_value(item, "category_name", "") or ""),
            str(_get_value(item, "shop_name", "") or ""),
        ]
    ).lower()


def _specialization_penalty(item: Any, intent: dict[str, Any]) -> Decimal:
    original = str(intent.get("original_text", "") or "").lower()
    haystack = _item_haystack(item)

    penalty = Decimal("0")
    special_tokens = ["内衣", "婴儿", "宝宝", "儿童", "宠物", "猫", "狗", "奶瓶", "厨房"]
    for token in special_tokens:
        if token in haystack and token not in original:
            penalty += Decimal("18")

    commodity = str(intent.get("commodity") or "").strip().lower()
    if commodity and commodity not in haystack:
        penalty += Decimal("8")

    return penalty


def _preference_score(item: Any, intent: dict[str, Any]) -> Decimal:
    token_hits = Decimal(_token_match_count(item, intent.get("search_tokens", [])))
    sales_volume = _safe_decimal(_get_value(item, "sales_volume", 0) or 0)
    commission_rate = _safe_decimal(_get_value(item, "commission_rate", 0) or 0)
    merchant_health = _safe_decimal(_get_value(item, "merchant_health_score", 0) or 0)
    coupon_price = _safe_decimal(_get_value(item, "coupon_price", 0) or 0)
    discount = _discount_amount(item)

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
    if intent.get("wants_self_operated") and str(_get_value(item, "owner", "") or "") == "g":
        score += Decimal("12")

    score -= _specialization_penalty(item, intent)
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


def _item_identity(item: Any) -> tuple[str, str]:
    item_id = _get_value(item, "id")
    if item_id not in (None, ""):
        return ("id", str(item_id))

    jd_sku_id = _get_value(item, "jd_sku_id")
    if jd_sku_id not in (None, ""):
        return ("jd_sku_id", str(jd_sku_id))

    short_url = _get_value(item, "short_url")
    if short_url not in (None, ""):
        return ("short_url", str(short_url))

    title = _get_value(item, "title", "")
    return ("title", str(title))


def _norm_pick_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _same_category(a: Any, b: Any) -> bool:
    av = _norm_pick_text(_get_value(a, "category_name", ""))
    bv = _norm_pick_text(_get_value(b, "category_name", ""))
    return bool(av and bv and av == bv)


def _same_shop(a: Any, b: Any) -> bool:
    av = _norm_pick_text(_get_value(a, "shop_name", ""))
    bv = _norm_pick_text(_get_value(b, "shop_name", ""))
    return bool(av and bv and av == bv)


def select_three_products(items: list[Any], intent: dict[str, Any]) -> list[tuple[str, Any]]:
    if not items:
        return []

    remaining = list(items)
    selected: list[tuple[str, Any]] = []

    best_fit = max(remaining, key=lambda p: _preference_score(p, intent))
    selected.append(("最符合你需求", best_fit))
    best_fit_key = _item_identity(best_fit)
    remaining = [p for p in remaining if _item_identity(p) != best_fit_key]

    if remaining:
        diverse_pool = [p for p in remaining if not _same_category(p, best_fit)]
        if not diverse_pool:
            diverse_pool = [p for p in remaining if not _same_shop(p, best_fit)]
        if not diverse_pool:
            diverse_pool = remaining

        best_sales = max(
            diverse_pool,
            key=lambda p: (
                _safe_decimal(_get_value(p, "sales_volume", 0) or 0),
                _preference_score(p, intent),
                _safe_decimal(_get_value(p, "merchant_health_score", 0) or 0),
            ),
        )
        selected.append(("下单热度更高", best_sales))
        best_sales_key = _item_identity(best_sales)
        remaining = [p for p in remaining if _item_identity(p) != best_sales_key]

    if remaining:
        chosen_items = [item for _, item in selected]
        diverse_pool = [
            p for p in remaining
            if all(not _same_category(p, chosen) for chosen in chosen_items)
        ]
        if not diverse_pool:
            diverse_pool = [
                p for p in remaining
                if all(not _same_shop(p, chosen) for chosen in chosen_items)
            ]
        if not diverse_pool:
            diverse_pool = remaining

        safest = max(
            diverse_pool,
            key=lambda p: (
                _preference_score(p, intent),
                _safe_decimal(_get_value(p, "merchant_health_score", 0) or 0),
                _safe_decimal(_get_value(p, "commission_rate", 0) or 0),
            ),
        )
        selected.append(("口碑与店铺更稳", safest))

    return selected


def build_product_link(item: Any, openid: str, *, scene: str, slot: int) -> str:
    product_id = _get_value(item, "id")
    short_url = _get_value(item, "short_url")
    product_url = _get_value(item, "product_url")

    if product_id:
        return f"{BASE_URL}/api/promotion/redirect?wechat_openid={openid}&product_id={product_id}&scene={scene}&slot={slot}"
    return short_url or product_url or ""


def build_product_block(role_label: str, item: Any, openid: str, *, slot: int) -> str:
    title = _short_title(_get_value(item, "title", "优选商品"))
    coupon_price = _safe_decimal(_get_value(item, "coupon_price", 0) or 0)
    price = _safe_decimal(_get_value(item, "price", 0) or 0)
    display_price = coupon_price if coupon_price > 0 else price
    link = build_product_link(item, openid, scene="wechat_reply", slot=slot)
    shop_name = _get_value(item, "shop_name", None) or "店铺信息待补充"

    if isinstance(item, dict) and item.get("source") == "jd_live":
        reason = item.get("reason") or "当前关键词实时检索命中，适合直接看看"
    else:
        reason = generate_reason(item)

    return (
        f"{role_label}\n"
        f"{title}\n"
        f"到手参考：¥{display_price:.2f}\n"
        f"店铺：{shop_name}\n"
        f"理由：{reason}\n"
        f"查看链接：{link}"
    )


def build_recommendation_text(selected: list[tuple[str, Any]], openid: str, intent: dict[str, Any], *, source_label: str = "local") -> str:
    if not selected:
        return get_copy("no_result_text") + "\n\n" + get_copy("category_gap_text")

    if source_label == "jd_live":
        intro = "我刚刚按你的关键词做了实时检索，再把高风险商品过滤掉，先给你挑 3 个更值得看的："
    elif intent.get("wants_low_price"):
        intro = "我先偏向价格和到手价给你筛了一轮，再把高风险商品过滤掉，给你挑了 3 个更值得看的："
    elif intent.get("wants_quality"):
        intro = "我先偏向质量、口碑和店铺稳定性给你筛了一轮，再把高风险商品过滤掉，给你挑了 3 个更值得看的："
    else:
        intro = "我先按你的需求，从价格、口碑、店铺稳定性里筛了一轮，再把高风险商品过滤掉，给你挑了 3 个更值得看的："

    blocks = []
    for idx, (role_label, item) in enumerate(selected, start=1):
        blocks.append(f"{idx}.\n{build_product_block(role_label, item, openid, slot=idx)}")

    return f"{intro}\n\n" + "\n\n".join(blocks) + f"\n\n{get_copy('retry_hint_text')}"


def _item_image_url(item: Any) -> str:
    for key in ("image_url", "main_image_url", "image", "white_image"):
        value = str(_get_value(item, key, "") or "").strip()
        if value:
            return value
    return ""


def _item_value_line(item: Any) -> str:
    price = _safe_decimal(_get_value(item, "price", 0) or 0)
    coupon_price = _safe_decimal(_get_value(item, "coupon_price", 0) or 0)
    sales = _safe_int(_get_value(item, "sales_volume", 0) or 0)

    effective = coupon_price if coupon_price > 0 and (price <= 0 or coupon_price <= price) else price
    saved = price - effective if price > 0 and effective > 0 and effective < price else Decimal("0")

    if saved > 0:
        left = f"省¥{saved:.0f}" if saved >= 10 else f"省¥{saved:.2f}".rstrip("0").rstrip(".")
    elif effective > 0:
        left = f"到手¥{effective:.2f}".rstrip("0").rstrip(".")
    else:
        left = "点开看实时价"

    if sales >= 10000:
        return f"{left}｜热销{sales / 10000:.1f}万+".replace(".0万+", "万+")
    if sales >= 100:
        return f"{left}｜热销{sales}+"
    return left


def build_recommendation_news_articles(selected: list[tuple[str, Any]], openid: str, *, scene: str = "product_request") -> list[dict[str, str]]:
    articles: list[dict[str, str]] = []

    for idx, (role_label, item) in enumerate(selected[:3], start=1):
        title_raw = str(_get_value(item, "title", "优选商品") or "优选商品").strip()
        role = str(role_label or "更值得看").strip()
        value_line = _item_value_line(item)
        shop_name = str(_get_value(item, "shop_name", "") or "").strip()
        reason = str(_get_value(item, "reason", "") or "").strip()

        if not reason:
            if isinstance(item, dict) and item.get("source") == "jd_live":
                reason = "实时检索命中，已过滤高风险商品。"
            else:
                reason = generate_reason(item)

        desc_parts = [f"{role}｜{value_line}"]
        if shop_name:
            desc_parts.append(shop_name)
        if reason:
            desc_parts.append(reason)

        url = build_product_link(item, openid, scene=scene, slot=idx)
        pic_url = _item_image_url(item)

        if not url:
            continue

        articles.append(
            {
                "title": _short_title(title_raw, 24)[:28],
                "description": "｜".join(desc_parts)[:120],
                "pic_url": pic_url,
                "url": url,
            }
        )

    return articles


def get_recommendation_news_articles(db: Session, openid: str, content: str) -> list[dict[str, str]]:
    intent = parse_product_intent(content)
    if not intent["shopping_intent"]:
        return []

    adult_verified = _resolve_adult_verified(db, openid)
    local_candidates = search_candidate_products(db, intent, adult_verified=adult_verified, limit=60)

    if not local_candidates and intent.get("commodity"):
        fallback_intent = dict(intent)
        fallback_intent["search_tokens"] = [intent["commodity"]]
        local_candidates = search_candidate_products(db, fallback_intent, adult_verified=adult_verified, limit=60)
        intent = fallback_intent

    rules = load_live_search_rules()
    if len(local_candidates) >= int(rules["local_result_threshold"]):
        selected = select_three_products(local_candidates, intent)
        return build_recommendation_news_articles(selected, openid, scene="product_request")

    live_candidates = _search_live_fallback(intent, adult_verified=adult_verified)
    if live_candidates:
        selected = select_three_products(live_candidates, intent)
        return build_recommendation_news_articles(selected, openid, scene="product_request_live")

    selected = select_three_products(local_candidates, intent)
    return build_recommendation_news_articles(selected, openid, scene="product_request")


def build_adult_gate_text(openid: str) -> str:
    verify_url = build_adult_verification_url(openid)
    return (
        "这类商品属于限制级内容，系统不会主动推荐。\n"
        "如你已年满18岁，可先完成成年声明，再继续被动查看：\n"
        f"{verify_url}\n\n"
        "完成后你可以重新发送商品名称，我再按规则帮你筛选。"
    )


def _search_live_fallback(intent: dict[str, Any], *, adult_verified: bool) -> list[dict[str, Any]]:
    query_text = intent.get("commodity") or " ".join(intent.get("search_tokens", []))
    query_text = (query_text or "").strip()
    if not query_text:
        return []
    try:
        return search_live_jd_products(query_text=query_text, adult_verified=adult_verified)
    except Exception:
        return []


def get_recommendation_reply(db: Session, openid: str, content: str) -> str:
    intent = parse_product_intent(content)
    if not intent["shopping_intent"]:
        return get_copy("non_shopping_redirect_text")

    adult_verified = _resolve_adult_verified(db, openid)
    local_candidates = search_candidate_products(db, intent, adult_verified=adult_verified, limit=60)

    if not local_candidates and not adult_verified and _restricted_candidates_exist(db, intent):
        return build_adult_gate_text(openid)

    if not local_candidates and intent.get("commodity"):
        fallback_intent = dict(intent)
        fallback_intent["search_tokens"] = [intent["commodity"]]
        local_candidates = search_candidate_products(db, fallback_intent, adult_verified=adult_verified, limit=60)
        intent = fallback_intent

    if not local_candidates and not adult_verified and _restricted_candidates_exist(db, intent):
        return build_adult_gate_text(openid)

    rules = load_live_search_rules()
    if len(local_candidates) >= int(rules["local_result_threshold"]):
        selected = select_three_products(local_candidates, intent)
        return build_recommendation_text(selected, openid, intent, source_label="local")

    live_candidates = _search_live_fallback(intent, adult_verified=adult_verified)

    if live_candidates:
        selected = select_three_products(live_candidates, intent)
        return build_recommendation_text(selected, openid, intent, source_label="jd_live")

    selected = select_three_products(local_candidates, intent)
    return build_recommendation_text(selected, openid, intent, source_label="local")


def get_help_reply() -> str:
    return get_copy("help_text")


def get_welcome_reply() -> str:
    return get_copy("welcome_text")
