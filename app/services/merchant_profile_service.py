from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.merchant_profile import MerchantProfile


def _to_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _pick_shop_info(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("shopInfo") or {}


def _pick_shop_id(item: dict[str, Any]) -> str | None:
    shop_info = _pick_shop_info(item)
    shop_id = shop_info.get("shopId") or item.get("shop_id") or item.get("shopId")
    if shop_id in (None, ""):
        return None
    return str(shop_id)


def _pick_shop_name(item: dict[str, Any]) -> str | None:
    shop_info = _pick_shop_info(item)
    return shop_info.get("shopName") or item.get("shop_name") or item.get("shopName")


def _pick_category_name(item: dict[str, Any]) -> str | None:
    category_info = item.get("categoryInfo") or {}
    return (
        item.get("category_name")
        or category_info.get("cid3Name")
        or category_info.get("cid2Name")
        or category_info.get("cid1Name")
    )


def _pick_price(item: dict[str, Any]) -> float:
    price_info = item.get("priceInfo") or {}
    value = (
        price_info.get("lowestCouponPrice")
        or price_info.get("lowestPrice")
        or price_info.get("price")
        or item.get("coupon_price")
        or item.get("price")
        or 0
    )
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def build_category_price_medians(items: list[dict[str, Any]] | None) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for item in items or []:
        category_name = _pick_category_name(item)
        if not category_name:
            continue
        grouped.setdefault(category_name, []).append(_pick_price(item))

    medians: dict[str, float] = {}
    for category_name, values in grouped.items():
        values = sorted(v for v in values if v >= 0)
        if not values:
            continue
        n = len(values)
        if n % 2 == 1:
            medians[category_name] = values[n // 2]
        else:
            medians[category_name] = round((values[n // 2 - 1] + values[n // 2]) / 2, 2)
    return medians


def classify_price_band(
    item: dict[str, Any],
    category_price_medians: dict[str, float] | None = None,
    category_median_price: float | int | None = None,
) -> str:
    price = _pick_price(item)

    if category_median_price not in (None, 0):
        median = float(category_median_price)
    else:
        category_price_medians = category_price_medians or {}
        category_name = _pick_category_name(item)
        median = float(category_price_medians.get(category_name or "", 0) or 0)

    if median <= 0:
        return "mid"
    if price <= median * 0.85:
        return "low"
    if price >= median * 1.15:
        return "high"
    return "mid"


def _build_risk_flags(
    *,
    user_evaluate_score: float | None,
    after_service_score: float | None,
    logistics_lvyue_score: float | None,
    score_rank_rate: float | None,
    price_band: str | None,
) -> str | None:
    flags: list[str] = []

    if user_evaluate_score is not None and user_evaluate_score <= 8.5:
        flags.append("poor_reputation")
    if after_service_score is not None and after_service_score < 8.5:
        flags.append("poor_after_sales")
    if logistics_lvyue_score is not None and logistics_lvyue_score < 8.5:
        flags.append("poor_fulfillment")
    if score_rank_rate is not None and score_rank_rate < 30:
        flags.append("low_rank_rate")
    if price_band == "high":
        flags.append("price_too_high")

    return ",".join(flags) if flags else None


def _calc_health_score(
    *,
    owner: str | None,
    user_evaluate_score: float | None,
    after_service_score: float | None,
    logistics_lvyue_score: float | None,
    score_rank_rate: float | None,
) -> float:
    if owner == "g" and all(v is None for v in [user_evaluate_score, after_service_score, logistics_lvyue_score, score_rank_rate]):
        return 85.0

    parts: list[float] = []

    if user_evaluate_score is not None:
        parts.append(user_evaluate_score * 10)
    if after_service_score is not None:
        parts.append(after_service_score * 10)
    if logistics_lvyue_score is not None:
        parts.append(logistics_lvyue_score * 10)
    if score_rank_rate is not None:
        parts.append(score_rank_rate)

    if not parts:
        return 70.0

    return round(sum(parts) / len(parts), 2)


def build_merchant_snapshot(
    item: dict[str, Any],
    *,
    category_price_medians: dict[str, float] | None = None,
    category_median_price: float | int | None = None,
    source: str = "jd",
) -> dict[str, Any] | None:
    shop_info = _pick_shop_info(item)
    shop_id = _pick_shop_id(item)
    if not shop_id:
        return None

    owner = item.get("owner")
    user_evaluate_score = _to_float(shop_info.get("userEvaluateScore") or item.get("user_evaluate_score"))
    after_service_score = _to_float(shop_info.get("afterServiceScore") or item.get("after_service_score"))
    logistics_lvyue_score = _to_float(shop_info.get("logisticsLvyueScore") or item.get("logistics_lvyue_score"))
    score_rank_rate = _to_float(shop_info.get("scoreRankRate") or item.get("score_rank_rate"))

    price_band = classify_price_band(
        item,
        category_price_medians=category_price_medians,
        category_median_price=category_median_price,
    )

    merchant_health_score = _calc_health_score(
        owner=owner,
        user_evaluate_score=user_evaluate_score,
        after_service_score=after_service_score,
        logistics_lvyue_score=logistics_lvyue_score,
        score_rank_rate=score_rank_rate,
    )
    risk_flags = _build_risk_flags(
        user_evaluate_score=user_evaluate_score,
        after_service_score=after_service_score,
        logistics_lvyue_score=logistics_lvyue_score,
        score_rank_rate=score_rank_rate,
        price_band=price_band,
    )

    risk_flag_list = [flag for flag in (risk_flags or "").split(",") if flag]
    if price_band == "high" and "price_too_high" not in risk_flag_list:
        risk_flag_list.append("price_too_high")
    risk_flags = ",".join(risk_flag_list) if risk_flag_list else None

    if owner == "g":
        recommendable = merchant_health_score >= 60.0
    else:
        recommendable = merchant_health_score >= 60.0 and not risk_flags

    snapshot = {
        "shop_id": shop_id,
        "shop_name": _pick_shop_name(item),
        "shop_label": shop_info.get("shopLabel") or item.get("shop_label"),
        "owner": owner,
        "user_evaluate_score": user_evaluate_score,
        "after_service_score": after_service_score,
        "logistics_lvyue_score": logistics_lvyue_score,
        "score_rank_rate": score_rank_rate,
        "merchant_health_score": merchant_health_score,
        "risk_flags": risk_flags,
        "recommendable": recommendable,
        "source": source,
        "last_sync_at": datetime.now(timezone.utc),
        "category_name": _pick_category_name(item),
        "price_value": _pick_price(item),
        "price_band": price_band,
    }
    return snapshot


def build_merchant_profile_payload(
    item: dict[str, Any],
    *,
    source: str = "jd",
    category_price_medians: dict[str, float] | None = None,
    category_median_price: float | int | None = None,
) -> dict[str, Any] | None:
    snapshot = build_merchant_snapshot(
        item,
        category_price_medians=category_price_medians,
        category_median_price=category_median_price,
        source=source,
    )
    if not snapshot:
        return None

    return {
        "shop_id": snapshot["shop_id"],
        "shop_name": snapshot["shop_name"],
        "shop_label": snapshot["shop_label"],
        "owner": snapshot["owner"],
        "user_evaluate_score": snapshot["user_evaluate_score"],
        "after_service_score": snapshot["after_service_score"],
        "logistics_lvyue_score": snapshot["logistics_lvyue_score"],
        "score_rank_rate": snapshot["score_rank_rate"],
        "merchant_health_score": snapshot["merchant_health_score"],
        "risk_flags": snapshot["risk_flags"],
        "recommendable": snapshot["recommendable"],
        "source": snapshot["source"],
        "last_sync_at": snapshot["last_sync_at"],
    }


def upsert_merchant_profile(
    db: Session,
    item: dict[str, Any],
    *,
    source: str = "jd",
    category_price_medians: dict[str, float] | None = None,
    category_median_price: float | int | None = None,
) -> MerchantProfile | None:
    payload = build_merchant_profile_payload(
        item,
        source=source,
        category_price_medians=category_price_medians,
        category_median_price=category_median_price,
    )
    if not payload:
        return None

    shop_id = payload["shop_id"]
    profile = db.query(MerchantProfile).filter(MerchantProfile.shop_id == shop_id).first()

    if profile is None:
        profile = MerchantProfile(shop_id=shop_id)
        db.add(profile)
        db.flush()

    for key, value in payload.items():
        setattr(profile, key, value)

    db.flush()
    return profile


def upsert_merchant_profile_from_jd_item(
    db: Session,
    item: dict[str, Any],
    *,
    source: str = "jd",
    category_price_medians: dict[str, float] | None = None,
    category_median_price: float | int | None = None,
) -> MerchantProfile | None:
    return upsert_merchant_profile(
        db,
        item,
        source=source,
        category_price_medians=category_price_medians,
        category_median_price=category_median_price,
    )


def sync_merchant_profile_from_jd_item(
    db: Session,
    item: dict[str, Any],
    *,
    source: str = "jd",
    category_price_medians: dict[str, float] | None = None,
    category_median_price: float | int | None = None,
) -> MerchantProfile | None:
    return upsert_merchant_profile(
        db,
        item,
        source=source,
        category_price_medians=category_price_medians,
        category_median_price=category_median_price,
    )


def list_merchant_profiles(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        db.query(MerchantProfile)
        .order_by(MerchantProfile.last_sync_at.desc(), MerchantProfile.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "shop_id": row.shop_id,
            "shop_name": row.shop_name,
            "merchant_health_score": row.merchant_health_score,
            "risk_flags": row.risk_flags,
            "recommendable": row.recommendable,
        }
        for row in rows
    ]
