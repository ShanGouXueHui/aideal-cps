from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.free_llm.semantic_review_service import review_proactive_categories_with_free_llm


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "proactive_recommend_rules.json"
RUN_DIR = PROJECT_ROOT / "run"
DYNAMIC_WHITELIST_PATH = RUN_DIR / "proactive_recommend_whitelist.json"


DEFAULT_RISK_KEYWORDS = [
    "处方", "处方药", "非处方药", "otc", "药用", "皮肤用药",
    "农药", "杀虫", "呋虫胺", "噻虫胺", "氨茶碱",
    "白酒", "红酒", "啤酒", "威士忌", "洋酒",
    "防狼", "喷雾", "辣椒水", "电击", "枪", "刀",
    "维修", "上门", "本地服务",
    "成人用品", "情趣", "性欲", "荷尔蒙", "催情",
    "试用", "试用装", "体验", "体验装", "拉新", "拉新装",
    "新人到手0.01", "尝鲜", "尝鲜装", "旅行装", "便携装",
    "随机发", "单包", "单支", "单片", "1包", "1支", "1片",
]


def _load_rules() -> dict[str, Any]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip().lower() for x in value if str(x).strip()]


def _contains_any(text: str, words: list[str]) -> bool:
    lower = str(text or "").lower()
    return any(w and w in lower for w in words)


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _to_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0


def _effective_price(product: Product) -> float:
    price = _to_float(getattr(product, "price", None))
    coupon_price = _to_float(getattr(product, "coupon_price", None))
    if coupon_price > 0 and (price <= 0 or coupon_price <= price):
        return coupon_price
    return price


def _saved_amount(product: Product) -> float:
    price = _to_float(getattr(product, "price", None))
    effective = _effective_price(product)
    if price > 0 and effective > 0 and effective < price:
        return price - effective
    return 0.0


def _source_match(product: Product, prefixes: list[str]) -> bool:
    if not prefixes:
        return True
    tags = str(getattr(product, "ai_tags", "") or "")
    return any(prefix and prefix in tags for prefix in prefixes)


def _score_product(product: Product) -> float:
    sales = _to_int(getattr(product, "sales_volume", None))
    commission = _to_float(getattr(product, "estimated_commission", None))
    saved = _saved_amount(product)
    health = _to_float(getattr(product, "merchant_health_score", None))

    return round(
        min(math.log1p(max(sales, 0)), 13) * 2.0
        + min(max(commission, 0), 20) * 3.0
        + min(max(saved, 0), 50) * 0.6
        + min(max(health, 0), 100) * 0.03,
        6,
    )


def refresh_proactive_recommend_whitelist(db: Session) -> dict[str, Any]:
    rules = _load_rules()
    if not rules.get("dynamic_whitelist_enabled", True):
        return {"status": "disabled"}

    source_prefixes = _text_list(rules.get("auto_whitelist_source_tag_prefixes")) or ["榜单:", "用户请求:"]
    exclude_category_keywords = _text_list(rules.get("exclude_category_keywords"))
    exclude_title_keywords = _text_list(rules.get("exclude_title_keywords"))
    exclude_shop_keywords = _text_list(rules.get("exclude_shop_keywords"))
    hard_risk_keywords = _text_list(rules.get("auto_whitelist_risk_keywords")) or DEFAULT_RISK_KEYWORDS

    min_effective_price = _to_float(rules.get("min_effective_price", rules.get("min_coupon_price", 0)))
    max_effective_price = _to_float(rules.get("max_effective_price", 0))
    min_estimated_commission = _to_float(rules.get("min_estimated_commission", 0))
    min_sales_volume = _to_int(rules.get("min_sales_volume", 0))
    max_categories = max(8, _to_int(rules.get("auto_whitelist_max_categories", 80)) or 80)
    top_product_limit = max(20, _to_int(rules.get("auto_whitelist_top_product_limit", 240)) or 240)
    min_candidates = max(5, _to_int(rules.get("auto_whitelist_min_candidates", 15)) or 15)

    rows = (
        db.query(Product)
        .filter(Product.status == "active")
        .filter(Product.compliance_level == "normal")
        .filter(Product.allow_proactive_push == True)
        .filter(Product.allow_partner_share == True)
        .filter(Product.merchant_recommendable == True)
        .all()
    )

    candidates: list[tuple[float, Product]] = []
    rejected = Counter()

    for product in rows:
        title = str(getattr(product, "title", "") or "")
        category = str(getattr(product, "category_name", "") or "")
        shop = str(getattr(product, "shop_name", "") or "")
        effective_price = _effective_price(product)
        estimated_commission = _to_float(getattr(product, "estimated_commission", None))
        sales_volume = _to_int(getattr(product, "sales_volume", None))

        if not _source_match(product, source_prefixes):
            rejected["source_miss"] += 1
            continue
        if _contains_any(category, exclude_category_keywords):
            rejected["exclude_category"] += 1
            continue
        if _contains_any(title, exclude_title_keywords):
            rejected["exclude_title"] += 1
            continue
        if _contains_any(shop, exclude_shop_keywords):
            rejected["exclude_shop"] += 1
            continue
        if _contains_any(title, hard_risk_keywords) or _contains_any(category, hard_risk_keywords):
            rejected["hard_risk_keyword"] += 1
            continue
        if min_effective_price > 0 and (effective_price <= 0 or effective_price < min_effective_price):
            rejected["price_low"] += 1
            continue
        if max_effective_price > 0 and effective_price > max_effective_price:
            rejected["price_high"] += 1
            continue
        if min_estimated_commission > 0 and estimated_commission < min_estimated_commission:
            rejected["commission_low"] += 1
            continue
        if min_sales_volume > 0 and sales_volume < min_sales_volume:
            rejected["sales_low"] += 1
            continue

        candidates.append((_score_product(product), product))

    candidates.sort(key=lambda item: item[0], reverse=True)

    category_counter: Counter[str] = Counter()
    derived_categories: list[str] = []
    top_rows: list[dict[str, Any]] = []

    for score, product in candidates[:top_product_limit]:
        category = str(getattr(product, "category_name", "") or "").strip()
        if not category:
            continue

        category_counter[category] += 1
        if category not in derived_categories:
            derived_categories.append(category)

        if len(top_rows) < 80:
            top_rows.append(
                {
                    "id": int(product.id),
                    "jd_sku_id": product.jd_sku_id,
                    "title": product.title,
                    "category_name": product.category_name,
                    "price": _to_float(product.price),
                    "coupon_price": _to_float(product.coupon_price),
                    "estimated_commission": _to_float(product.estimated_commission),
                    "sales_volume": _to_int(product.sales_volume),
                    "merchant_health_score": _to_float(product.merchant_health_score) if product.merchant_health_score is not None else None,
                    "score": score,
                    "ai_tags": product.ai_tags,
                    "last_sync_at": str(product.last_sync_at),
                }
            )

    if len(candidates) < min_candidates or len(derived_categories) < 3:
        previous = {}
        if DYNAMIC_WHITELIST_PATH.exists():
            try:
                previous = json.loads(DYNAMIC_WHITELIST_PATH.read_text(encoding="utf-8"))
            except Exception:
                previous = {}

        return {
            "status": "skipped",
            "reason": "not_enough_candidates",
            "candidate_count": len(candidates),
            "derived_category_count": len(derived_categories),
            "previous_category_count": len(previous.get("include_category_keywords", [])) if isinstance(previous, dict) else 0,
            "rejected": dict(rejected),
        }

    semantic_review = review_proactive_categories_with_free_llm(
        categories=derived_categories[:max_categories],
        top_rows=top_rows,
        rejected=dict(rejected),
    )
    include_categories = semantic_review.get("include_category_keywords") or derived_categories[:max_categories]

    payload = {
        "status": "success",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "auto_dynamic_whitelist_from_jd_ranking_user_request_and_free_llm_review",
        "source_tag_prefixes": source_prefixes,
        "include_category_keywords": include_categories,
        "candidate_count": len(candidates),
        "derived_category_count": len(include_categories),
        "raw_derived_category_count": len(derived_categories[:max_categories]),
        "category_counter_top": category_counter.most_common(60),
        "rejected": dict(rejected),
        "semantic_review": semantic_review,
        "top_rows": top_rows,
    }

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    DYNAMIC_WHITELIST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
