from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any

from sqlalchemy.orm import Session

from app.models.merchant_profile import MerchantProfile


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _category_name(item: dict[str, Any]) -> str:
    category_info = item.get("categoryInfo") or {}
    return (
        category_info.get("cid3Name")
        or category_info.get("cid2Name")
        or category_info.get("cid1Name")
        or "unknown"
    )


def build_category_price_medians(goods: list[dict[str, Any]]) -> dict[str, float]:
    price_map: dict[str, list[float]] = {}
    for item in goods:
        category_name = _category_name(item)
        price = _to_float((item.get("priceInfo") or {}).get("price"))
        if price is None or price <= 0:
            continue
        price_map.setdefault(category_name, []).append(price)

    return {category: float(median(values)) for category, values in price_map.items() if values}


def build_merchant_snapshot(
    item: dict[str, Any],
    *,
    category_median_price: float | None = None,
) -> dict[str, Any]:
    shop_info = item.get("shopInfo") or {}
    price = _to_float((item.get("priceInfo") or {}).get("price"))

    shop_id = shop_info.get("shopId")
    shop_name = shop_info.get("shopName")
    shop_label = str(shop_info.get("shopLabel") or "")
    owner = str(item.get("owner") or "")

    user_evaluate_score = _to_float(shop_info.get("userEvaluateScore"))
    after_service_score = _to_float(shop_info.get("afterServiceScore"))
    logistics_lvyue_score = _to_float(shop_info.get("logisticsLvyueScore"))
    score_rank_rate = _to_float(shop_info.get("scoreRankRate"))

    # 中性基线，避免“字段缺失 = 高风险”
    health_score = 70.0
    risk_flags: list[str] = []

    if user_evaluate_score is not None:
        if user_evaluate_score >= 9.5:
            health_score += 8.0
        elif user_evaluate_score >= 9.0:
            health_score += 4.0
        else:
            health_score -= 10.0
            risk_flags.append("poor_reputation")

    if after_service_score is not None:
        if after_service_score >= 9.5:
            health_score += 6.0
        elif after_service_score >= 9.0:
            health_score += 3.0
        else:
            health_score -= 8.0
            risk_flags.append("poor_after_sales")

    if logistics_lvyue_score is not None:
        if logistics_lvyue_score >= 9.2:
            health_score += 5.0
        elif logistics_lvyue_score >= 8.8:
            health_score += 2.0
        else:
            health_score -= 6.0
            risk_flags.append("poor_fulfillment")

    if score_rank_rate is not None:
        if score_rank_rate >= 90:
            health_score += 5.0
        elif score_rank_rate >= 70:
            health_score += 2.0
        elif score_rank_rate < 50:
            health_score -= 5.0

    # 官方旗舰店 / 自营给正向加权
    if shop_label == "1":
        health_score += 4.0
    if owner == "g":
        health_score += 6.0

    if category_median_price and price and price > category_median_price * 1.25:
        risk_flags.append("price_too_high")
        health_score -= 8.0

    health_score = max(0.0, min(100.0, round(health_score, 2)))

    recommendable = True
    if health_score < 60.0:
        recommendable = False
    if "price_too_high" in risk_flags and ("poor_reputation" in risk_flags or "poor_after_sales" in risk_flags):
        recommendable = False

    return {
        "shop_id": str(shop_id) if shop_id is not None else "",
        "shop_name": shop_name,
        "shop_label": shop_label,
        "owner": owner or None,
        "user_evaluate_score": user_evaluate_score,
        "after_service_score": after_service_score,
        "logistics_lvyue_score": logistics_lvyue_score,
        "score_rank_rate": score_rank_rate,
        "merchant_health_score": health_score,
        "risk_flags": ",".join(sorted(set(risk_flags))) if risk_flags else None,
        "recommendable": recommendable,
        "source": "jd",
        "last_sync_at": datetime.now(timezone.utc),
    }


def upsert_merchant_profile(db: Session, snapshot: dict[str, Any]) -> tuple[MerchantProfile | None, str | None]:
    shop_id = snapshot.get("shop_id")
    if not shop_id:
        return None, None

    row = db.query(MerchantProfile).filter(MerchantProfile.shop_id == shop_id).first()
    if row:
        for key, value in snapshot.items():
            setattr(row, key, value)
        return row, "updated"

    row = MerchantProfile(**snapshot)
    db.add(row)
    return row, "inserted"
