from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.jd_union_workflow_service import JDUnionWorkflowService
from app.services import merchant_profile_service as _merchant_profile_service


def _merchant_profile_fallback(name: str):
    if "medians" in name:
        return lambda *args, **kwargs: {}
    if name.startswith(("build_", "get_", "calculate_", "classify_")):
        return lambda *args, **kwargs: {}
    if name.startswith(("list_", "collect_")):
        return lambda *args, **kwargs: []
    if name.startswith(("is_", "has_", "allow_")):
        return lambda *args, **kwargs: False
    return lambda *args, **kwargs: None


build_category_price_medians = getattr(
    _merchant_profile_service,
    "build_category_price_medians",
    _merchant_profile_fallback("build_category_price_medians"),
)
build_merchant_snapshot = getattr(
    _merchant_profile_service,
    "build_merchant_snapshot",
    _merchant_profile_fallback("build_merchant_snapshot"),
)
upsert_merchant_profile = getattr(
    _merchant_profile_service,
    "upsert_merchant_profile",
    _merchant_profile_fallback("upsert_merchant_profile"),
)

from app.services.product_compliance_service import enrich_product_payload_with_compliance


def _merchant_profiles_table_exists(db: Session) -> bool:
    try:
        return inspect(db.bind).has_table("merchant_profiles")
    except Exception:
        return False


def _pick_image_url(item: dict[str, Any]) -> str | None:
    image_info = item.get("imageInfo") or {}
    if image_info.get("whiteImage"):
        return image_info["whiteImage"]

    image_list = image_info.get("imageList") or []
    if isinstance(image_list, list) and image_list:
        return image_list[0].get("url")
    if isinstance(image_list, dict):
        url = image_list.get("url")
        if url:
            return url
    return None


def _coupon_summary(item: dict[str, Any]) -> str | None:
    coupon_info = item.get("couponInfo") or {}
    coupon_list = coupon_info.get("couponList") or []
    if isinstance(coupon_list, list) and coupon_list:
        first = coupon_list[0]
        quota = first.get("quota")
        discount = first.get("discount")
        if quota is not None and discount is not None:
            return f"满{quota}减{discount}"
    return None


def normalize_jd_item(
    item: dict[str, Any],
    short_url: str | None = None,
    merchant_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    price_info = item.get("priceInfo") or {}
    commission_info = item.get("commissionInfo") or {}
    category_info = item.get("categoryInfo") or {}
    shop_info = item.get("shopInfo") or {}
    resource_info = item.get("resourceInfo") or {}
    material_url = item.get("materialUrl")
    short_url = short_url or item.get("shortURL") or item.get("shortUrl") or item.get("clickURL")
    jd_sku_id = str(item.get("skuId") or item.get("spuid") or item.get("itemId") or material_url or "")
    merchant_snapshot = merchant_snapshot or {}

    payload = {
        "jd_sku_id": jd_sku_id,
        "title": item.get("skuName") or "unknown",
        "description": None,
        "image_url": _pick_image_url(item),
        "product_url": short_url or material_url,
        "material_url": material_url,
        "short_url": short_url,
        "category_name": category_info.get("cid3Name") or category_info.get("cid2Name") or category_info.get("cid1Name"),
        "shop_name": shop_info.get("shopName"),
        "shop_id": str(shop_info.get("shopId")) if shop_info.get("shopId") is not None else None,
        "price": Decimal(str(price_info.get("price") or 0)),
        "coupon_price": Decimal(str(price_info.get("lowestCouponPrice") or price_info.get("lowestPrice") or 0)),
        "commission_rate": float(commission_info.get("commissionShare") or 0),
        "estimated_commission": Decimal(str(commission_info.get("commission") or 0)),
        "sales_volume": int(item.get("inOrderCount30DaysSku") or item.get("inOrderCount30Days") or 0),
        "coupon_info": _coupon_summary(item),
        "ai_reason": None,
        "ai_tags": resource_info.get("eliteName"),
        "elite_id": int(resource_info.get("eliteId")) if resource_info.get("eliteId") is not None else None,
        "elite_name": resource_info.get("eliteName"),
        "owner": item.get("owner"),
        "merchant_health_score": merchant_snapshot.get("merchant_health_score"),
        "merchant_risk_flags": merchant_snapshot.get("risk_flags"),
        "merchant_recommendable": merchant_snapshot.get("recommendable", True),
        "status": "active",
        "last_sync_at": datetime.now(timezone.utc),
    }
    return enrich_product_payload_with_compliance(
        payload,
        forbid_types=item.get("forbidTypes") or [],
    )


def _find_pending_or_loaded_product(db: Session, jd_sku_id: str) -> Product | None:
    for obj in list(db.new):
        if isinstance(obj, Product) and getattr(obj, "jd_sku_id", None) == jd_sku_id:
            return obj
    for obj in list(db.identity_map.values()):
        if isinstance(obj, Product) and getattr(obj, "jd_sku_id", None) == jd_sku_id:
            return obj
    return None


def upsert_product(db: Session, payload: dict[str, Any]) -> tuple[Product, str]:
    jd_sku_id = str(payload["jd_sku_id"])

    pending = _find_pending_or_loaded_product(db, jd_sku_id)
    if pending is not None:
        for key, value in payload.items():
            setattr(pending, key, value)
        return pending, "updated"

    product = db.query(Product).filter(Product.jd_sku_id == jd_sku_id).first()
    if product:
        for key, value in payload.items():
            setattr(product, key, value)
        return product, "updated"

    product = Product(**payload)
    db.add(product)
    return product, "inserted"


def sync_jd_products(
    db: Session,
    *,
    elite_id: int,
    limit: int = 10,
    page_index: int = 1,
    page_size: int = 20,
    with_short_links: bool = True,
) -> dict[str, Any]:
    workflow = JDUnionWorkflowService()
    goods = workflow.query_goods(
        elite_id=elite_id,
        page_index=page_index,
        page_size=page_size,
    )[:limit]

    merchant_profiles_enabled = _merchant_profiles_table_exists(db)
    price_medians = build_category_price_medians(goods)
    inserted = 0
    updated = 0
    skipped_duplicates = 0
    rows: list[dict[str, Any]] = []
    seen_sku_ids: set[str] = set()

    for item in goods:
        raw_sku_id = str(item.get("skuId") or item.get("spuid") or item.get("itemId") or item.get("materialUrl") or "").strip()
        if not raw_sku_id:
            continue
        if raw_sku_id in seen_sku_ids:
            skipped_duplicates += 1
            continue
        seen_sku_ids.add(raw_sku_id)

        category_info = item.get("categoryInfo") or {}
        category_name = category_info.get("cid3Name") or category_info.get("cid2Name") or category_info.get("cid1Name") or "unknown"

        merchant_snapshot = build_merchant_snapshot(
            item,
            category_median_price=price_medians.get(category_name),
        )

        if merchant_profiles_enabled and merchant_snapshot:
            try:
                upsert_merchant_profile(db, merchant_snapshot)
            except Exception:
                db.rollback()

        material_url = item.get("materialUrl")
        api_short_url = item.get("shortURL") or item.get("shortUrl") or item.get("clickURL")
        short_url = api_short_url
        if not short_url and with_short_links and material_url:
            try:
                short_url = workflow.build_short_link(material_url)
            except Exception:
                short_url = None

        payload = normalize_jd_item(item, short_url=short_url, merchant_snapshot=merchant_snapshot)
        product, action = upsert_product(db, payload)

        if action == "inserted":
            inserted += 1
        else:
            updated += 1

        rows.append(
            {
                "jd_sku_id": product.jd_sku_id,
                "title": product.title,
                "short_url": product.short_url,
                "merchant_health_score": product.merchant_health_score,
                "merchant_recommendable": product.merchant_recommendable,
                "compliance_level": product.compliance_level,
                "allow_proactive_push": product.allow_proactive_push,
                "allow_partner_share": product.allow_partner_share,
                "action": action,
            }
        )

    db.commit()
    return {
        "elite_id": elite_id,
        "page_index": page_index,
        "limit": limit,
        "inserted": inserted,
        "updated": updated,
        "skipped_duplicates": skipped_duplicates,
        "total": len(rows),
        "rows": rows,
    }


# === exact price / review enrichment override ===
from decimal import Decimal as _ExactDecimal

_ORIG_NORMALIZE_JD_ITEM = normalize_jd_item

def _exact_to_decimal(value):
    try:
        if value in (None, ""):
            return None
        return _ExactDecimal(str(value))
    except Exception:
        return None

def _exact_to_int(value):
    try:
        if value in (None, ""):
            return None
        return int(str(value))
    except Exception:
        return None

def _exact_to_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None

def normalize_jd_item(
    item: dict[str, Any],
    short_url: str | None = None,
    merchant_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _ORIG_NORMALIZE_JD_ITEM(item, short_url=short_url, merchant_snapshot=merchant_snapshot)

    price_info = item.get("priceInfo") or {}
    purchase_info = item.get("purchasePriceInfo") or {}
    purchase_code = str(purchase_info.get("code") or "").strip()

    purchase_price = _exact_to_decimal(purchase_info.get("purchasePrice")) if purchase_code == "200" else None
    basis_price = _exact_to_decimal(purchase_info.get("thresholdPrice")) if purchase_code == "200" else None
    basis_price_type = _exact_to_int(purchase_info.get("basisPriceType")) if purchase_code == "200" else None

    raw_price = _exact_to_decimal(price_info.get("price"))
    raw_coupon_price = _exact_to_decimal(
        price_info.get("lowestCouponPrice") or price_info.get("lowestPrice")
    )

    exact_discount = bool(
        purchase_price is not None
        and basis_price is not None
        and basis_price_type == 1
        and purchase_price < basis_price
    )

    payload["price"] = raw_price or basis_price or purchase_price or payload.get("price")
    payload["coupon_price"] = purchase_price or raw_coupon_price or payload.get("coupon_price")
    payload["purchase_price"] = purchase_price
    payload["basis_price"] = basis_price
    payload["basis_price_type"] = basis_price_type
    payload["good_comments_share"] = _exact_to_float(item.get("goodCommentsShare"))
    payload["comment_count"] = _exact_to_int(item.get("comments"))
    payload["price_verified_at"] = datetime.now(timezone.utc) if purchase_code == "200" else payload.get("price_verified_at")
    payload["is_exact_discount"] = exact_discount

    return payload
