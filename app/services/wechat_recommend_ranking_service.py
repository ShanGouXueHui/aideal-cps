from __future__ import annotations

import math
import re
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default


def _brand_key(product: Any) -> str:
    shop_name = str(getattr(product, "shop_name", "") or "").strip().lower()
    if shop_name:
        return shop_name

    title = str(getattr(product, "title", "") or "").strip().lower()
    if not title:
        return ""

    head = re.split(r"[（(\\s\\-_/【\\[]", title, maxsplit=1)[0].strip()
    return head


def _category_key(product: Any) -> str:
    return str(getattr(product, "category_name", "") or "").strip().lower()


def score_product(product: Any, rules: dict) -> float:
    ranking_rules = (rules.get("ranking") or {})
    weights = ranking_rules.get("weights") or {}
    caps = ranking_rules.get("caps") or {}

    w_discount_rate = _safe_float(weights.get("discount_rate"), 0.25)
    w_delta_amount = _safe_float(weights.get("delta_amount"), 0.10)
    w_sales_volume = _safe_float(weights.get("sales_volume"), 0.35)
    w_comment_count = _safe_float(weights.get("comment_count"), 0.20)
    w_good_comment_rate = _safe_float(weights.get("good_comment_rate"), 0.10)

    delta_amount_max = _safe_float(caps.get("delta_amount_max"), 50.0)

    purchase_price = _safe_float(getattr(product, "purchase_price", 0))
    basis_price = _safe_float(getattr(product, "basis_price", 0))
    delta = max(basis_price - purchase_price, 0.0)
    discount_rate = (delta / basis_price) if basis_price > 0 else 0.0

    sales_volume = max(_safe_int(getattr(product, "sales_volume", 0)), 0)
    comment_count = max(_safe_int(getattr(product, "comment_count", 0)), 0)
    good_comment_rate = max(_safe_float(getattr(product, "good_comments_share", 0.0)), 0.0) / 100.0

    delta_amount_score = min(delta, delta_amount_max) / delta_amount_max if delta_amount_max > 0 else 0.0
    sales_volume_score = min(math.log10(sales_volume + 1) / 5.0, 1.0)
    comment_count_score = min(math.log10(comment_count + 1) / 5.0, 1.0)

    score = (
        discount_rate * w_discount_rate
        + delta_amount_score * w_delta_amount
        + sales_volume_score * w_sales_volume
        + comment_count_score * w_comment_count
        + good_comment_rate * w_good_comment_rate
    )
    return round(score, 6)


def filter_candidates(products: list[Any], rules: dict) -> list[Any]:
    pool_rules = (rules.get("pool_filters") or {})
    min_exact_delta = _safe_float(pool_rules.get("min_exact_delta"), 5.0)
    min_sales_volume = _safe_int(pool_rules.get("min_sales_volume"), 10)
    exclude_title_keywords = [
        str(x).strip() for x in (pool_rules.get("exclude_title_keywords") or []) if str(x).strip()
    ]

    rows: list[Any] = []
    for row in products:
        title = str(getattr(row, "title", "") or "")
        if exclude_title_keywords and any(keyword in title for keyword in exclude_title_keywords):
            continue

        purchase_price = _safe_float(getattr(row, "purchase_price", 0))
        basis_price = _safe_float(getattr(row, "basis_price", 0))
        delta = max(basis_price - purchase_price, 0.0)
        sales_volume = _safe_int(getattr(row, "sales_volume", 0), 0)

        if delta < min_exact_delta:
            continue
        if sales_volume < min_sales_volume:
            continue

        rows.append(row)

    return rows


def reorder_with_diversity(products: list[Any], rules: dict) -> list[Any]:
    diversity_rules = (rules.get("diversity") or {})
    avoid_same_brand = bool(diversity_rules.get("avoid_same_brand_in_batch", True))
    avoid_same_category = bool(diversity_rules.get("avoid_same_category_in_batch", True))

    if not products:
        return []

    remaining = list(products)
    ordered: list[Any] = []
    used_brand: set[str] = set()
    used_category: set[str] = set()

    while remaining:
        picked_index = None

        for idx, row in enumerate(remaining):
            brand = _brand_key(row)
            category = _category_key(row)

            brand_ok = (not avoid_same_brand) or (not brand) or (brand not in used_brand)
            category_ok = (not avoid_same_category) or (not category) or (category not in used_category)

            if brand_ok and category_ok:
                picked_index = idx
                break

        if picked_index is None:
            used_brand.clear()
            used_category.clear()
            picked_index = 0

        row = remaining.pop(picked_index)
        ordered.append(row)

        brand = _brand_key(row)
        category = _category_key(row)
        if brand:
            used_brand.add(brand)
        if category:
            used_category.add(category)

    return ordered


def select_batch_with_diversity(products: list[Any], rules: dict) -> list[Any]:
    diversity_rules = (rules.get("diversity") or {})
    batch_size = int(diversity_rules.get("batch_size", 3))
    avoid_same_brand = bool(diversity_rules.get("avoid_same_brand_in_batch", True))
    avoid_same_category = bool(diversity_rules.get("avoid_same_category_in_batch", True))

    if not products or batch_size <= 0:
        return []

    selected: list[Any] = []
    used_brand: set[str] = set()
    used_category: set[str] = set()

    # 第一轮：强约束，尽量品牌和类目都不重复
    for row in products:
        if len(selected) >= batch_size:
            break

        brand = _brand_key(row)
        category = _category_key(row)

        brand_ok = (not avoid_same_brand) or (not brand) or (brand not in used_brand)
        category_ok = (not avoid_same_category) or (not category) or (category not in used_category)

        if brand_ok and category_ok:
            selected.append(row)
            if brand:
                used_brand.add(brand)
            if category:
                used_category.add(category)

    # 第二轮：放宽类目，只卡品牌
    if len(selected) < batch_size:
        selected_ids = {getattr(x, "id", None) for x in selected}
        for row in products:
            if len(selected) >= batch_size:
                break
            if getattr(row, "id", None) in selected_ids:
                continue

            brand = _brand_key(row)
            brand_ok = (not avoid_same_brand) or (not brand) or (brand not in used_brand)
            if brand_ok:
                selected.append(row)
                if brand:
                    used_brand.add(brand)
                selected_ids.add(getattr(row, "id", None))

    # 第三轮：再补齐，不再卡
    if len(selected) < batch_size:
        selected_ids = {getattr(x, "id", None) for x in selected}
        for row in products:
            if len(selected) >= batch_size:
                break
            if getattr(row, "id", None) in selected_ids:
                continue
            selected.append(row)
            selected_ids.add(getattr(row, "id", None))

    return selected
