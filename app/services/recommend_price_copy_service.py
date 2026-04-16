from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.recommend_price_copy_config_service import load_recommend_price_copy_rules


def _rules() -> dict:
    return load_recommend_price_copy_rules()


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _basis_price_label(basis_price_type: int) -> str:
    rules = _rules()
    labels = rules.get("basis_price_type_labels", {})
    default_label = rules.get("labels", {}).get("jd_basis_price", "京东官网价")
    return labels.get(str(basis_price_type), default_label)


def price_snapshot(product: Any) -> dict[str, Any]:
    purchase_price = _to_decimal(getattr(product, "purchase_price", None))
    basis_price = _to_decimal(getattr(product, "basis_price", None))
    basis_price_type = _to_int(getattr(product, "basis_price_type", None))
    coupon_price = _to_decimal(getattr(product, "coupon_price", None))
    jd_price = _to_decimal(getattr(product, "price", None))

    exact_discount = (
        purchase_price > 0
        and basis_price > 0
        and basis_price_type == 1
        and purchase_price < basis_price
    )

    if exact_discount:
        delta = basis_price - purchase_price
        discount_rate = (float(delta / basis_price) if basis_price > 0 else 0.0)
        return {
            "exact_discount": True,
            "purchase_price": purchase_price,
            "basis_price": basis_price,
            "basis_price_type": basis_price_type,
            "basis_price_label": _basis_price_label(basis_price_type),
            "delta": delta,
            "discount_rate": discount_rate,
            "fallback_price": purchase_price
        }

    fallback_price = coupon_price if coupon_price > 0 else jd_price
    return {
        "exact_discount": False,
        "purchase_price": purchase_price if purchase_price > 0 else None,
        "basis_price": basis_price if basis_price > 0 else None,
        "basis_price_type": basis_price_type or None,
        "basis_price_label": _basis_price_label(basis_price_type),
        "delta": Decimal("0"),
        "discount_rate": 0.0,
        "fallback_price": fallback_price
    }


def price_text(product: Any) -> str:
    rules = _rules()
    labels = rules.get("labels", {})
    snap = price_snapshot(product)

    if snap["exact_discount"]:
        price_label = labels.get("price", "优惠价")
        basis_label = snap["basis_price_label"]
        return f"{price_label}￥{snap['purchase_price']:.2f}｜{basis_label}￥{snap['basis_price']:.2f}｜立省￥{snap['delta']:.2f}"

    return labels.get("fallback_price", "以下单页实时为准")


def h5_reason(product: Any) -> str:
    rules = _rules()
    thresholds = rules.get("discount_thresholds", {})
    maturity = rules.get("maturity_thresholds", {})
    copy_rules = rules.get("reason_copy", {})

    snap = price_snapshot(product)
    if not snap["exact_discount"]:
        return copy_rules.get("fallback", "价格以下单页实时信息为准，建议尽快确认。")

    delta_amount = float(snap["delta"])
    discount_rate = float(snap["discount_rate"])

    sales_volume = _to_int(getattr(product, "sales_volume", 0))
    comment_count = _to_int(getattr(product, "comment_count", 0))
    good_comment_rate = _to_float(getattr(product, "good_comments_share", 0.0)) / 100.0

    strong_amount = _to_float(thresholds.get("strong_amount", 20))
    medium_amount = _to_float(thresholds.get("medium_amount", 8))
    strong_rate = _to_float(thresholds.get("strong_rate", 0.30))
    medium_rate = _to_float(thresholds.get("medium_rate", 0.15))

    high_sales_volume = _to_int(maturity.get("high_sales_volume", 200))
    mid_sales_volume = _to_int(maturity.get("mid_sales_volume", 50))
    high_comment_count = _to_int(maturity.get("high_comment_count", 10000))
    mid_comment_count = _to_int(maturity.get("mid_comment_count", 3000))
    target_good_comment_rate = _to_float(maturity.get("good_comment_rate", 0.97))

    mature_enough = (
        sales_volume >= high_sales_volume
        or comment_count >= high_comment_count
        or (sales_volume >= mid_sales_volume and comment_count >= mid_comment_count and good_comment_rate >= target_good_comment_rate)
    )

    if (delta_amount >= strong_amount or discount_rate >= strong_rate) and mature_enough:
        return copy_rules.get("strong_discount_mature", "优惠明显，成交成熟，适合直接下单。")

    if delta_amount >= strong_amount or discount_rate >= strong_rate:
        return copy_rules.get("strong_discount", "价格优势明显，适合直接判断。")

    if mature_enough and (delta_amount >= medium_amount or discount_rate >= medium_rate):
        return copy_rules.get("mature_value", "价格和接受度都更稳，适合直接下单。")

    return copy_rules.get("balanced_value", "这单属于价格和接受度都比较均衡的选择。")
