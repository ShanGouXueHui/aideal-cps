from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any

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

build_category_price_medians = getattr(_merchant_profile_service, "build_category_price_medians", _merchant_profile_fallback("build_category_price_medians"))
build_merchant_snapshot = getattr(_merchant_profile_service, "build_merchant_snapshot", _merchant_profile_fallback("build_merchant_snapshot"))
upsert_merchant_profile = getattr(_merchant_profile_service, "upsert_merchant_profile", _merchant_profile_fallback("upsert_merchant_profile"))
from app.services.product_compliance_service import enrich_product_payload_with_compliance


def _find_pending_product_by_sku(db: Session, jd_sku_id: str) -> Product | None:
    target = str(jd_sku_id or "").strip()
    if not target:
        return None
    for obj in db.new:
        if isinstance(obj, Product) and str(getattr(obj, "jd_sku_id", "") or "").strip() == target:
            return obj
    return None


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



def _pick_comment_count(item: dict[str, Any]) -> int | None:
    comment_info = item.get("commentInfo") or {}
    for key in ("commentCount", "comments", "comment_count"):
        value = item.get(key)
        if value is None:
            value = comment_info.get(key)
        try:
            if value is not None and str(value).strip() != "":
                return int(float(str(value).replace(",", "")))
        except Exception:
            pass
    return None


def _pick_good_comments_share(item: dict[str, Any]) -> float | None:
    comment_info = item.get("commentInfo") or {}
    for key in ("goodCommentsShare", "good_comments_share", "goodCommentShare"):
        value = item.get(key)
        if value is None:
            value = comment_info.get(key)
        try:
            if value is not None and str(value).strip() != "":
                v = float(str(value).replace("%", "").strip())
                if v > 1:
                    v = v / 100.0
                return v
        except Exception:
            pass
    return None





def _price_snapshot_from_price_info(
    price_info: dict[str, Any],
    purchase_price_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build canonical JD Union price snapshot from goods.query/jingfen.query fields.

    Canonical rule:
    - basis_price: comparison/base price, normally thresholdPrice or priceInfo.price.
    - purchase_price: lowest positive purchasable price visible in JD Union fields.
      It must consider both purchasePriceInfo.purchasePrice and priceInfo.lowestCouponPrice,
      because either side can be lower depending on coupon/promotion composition.
    """
    purchase_price_info = purchase_price_info or {}

    def money(value: Any) -> Decimal:
        try:
            if value is None or str(value).strip() == "":
                return Decimal("0")
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    def first_positive(*values: Any) -> Decimal:
        for value in values:
            amount = money(value)
            if amount > 0:
                return amount
        return Decimal("0")

    def min_positive(*values: Any) -> Decimal:
        positives = [money(value) for value in values if money(value) > 0]
        return min(positives) if positives else Decimal("0")

    basis_price = first_positive(
        purchase_price_info.get("thresholdPrice"),
        purchase_price_info.get("basisPrice"),
        price_info.get("price"),
        price_info.get("lowestPrice"),
        price_info.get("lowestCouponPrice"),
    )

    purchase_price = min_positive(
        purchase_price_info.get("purchasePrice"),
        price_info.get("lowestCouponPrice"),
        price_info.get("lowestPrice"),
        price_info.get("price"),
    )

    if basis_price <= 0 and purchase_price > 0:
        basis_price = purchase_price
    if purchase_price <= 0 and basis_price > 0:
        purchase_price = basis_price
    if basis_price > 0 and purchase_price > 0 and basis_price < purchase_price:
        basis_price = purchase_price

    exact_discount = purchase_price > 0 and basis_price > purchase_price
    has_snapshot = purchase_price > 0 or basis_price > 0
    basis_type = purchase_price_info.get("basisPriceType") or price_info.get("lowestPriceType") or 1

    return {
        "purchase_price": purchase_price if purchase_price > 0 else None,
        "basis_price": basis_price if basis_price > 0 else None,
        "basis_price_type": int(basis_type) if str(basis_type).strip().isdigit() else 1,
        "is_exact_discount": bool(exact_discount),
        "price_verified_at": datetime.now(timezone.utc) if has_snapshot else None,
    }

def _extract_sku_id_from_material_url(material_url: str | None) -> str | None:
    text = str(material_url or "")
    m = re.search(r"/product/(\d+)\.html", text)
    if m:
        return m.group(1)
    m = re.search(r"/(\d+)\.html", text)
    if m:
        return m.group(1)
    return None


def _pick_jd_sku_id(item: dict[str, Any], material_url: str | None) -> str:
    for key in ("skuId", "wareId", "spuid"):
        value = item.get(key)
        if value is not None and str(value).strip().isdigit():
            return str(value).strip()

    parsed = _extract_sku_id_from_material_url(material_url)
    if parsed:
        return parsed

    for key in ("itemId", "oriItemId", "callerItemId"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    return str(material_url or "")


def normalize_jd_item(
    item: dict[str, Any],
    short_url: str | None = None,
    merchant_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    price_info = item.get("priceInfo") or {}
    purchase_price_info = item.get("purchasePriceInfo") or {}
    commission_info = item.get("commissionInfo") or {}
    category_info = item.get("categoryInfo") or {}
    shop_info = item.get("shopInfo") or {}
    resource_info = item.get("resourceInfo") or {}
    material_url = item.get("materialUrl")
    jd_sku_id = _pick_jd_sku_id(item, material_url)
    merchant_snapshot = merchant_snapshot or {}

    price_snapshot = _price_snapshot_from_price_info(price_info, purchase_price_info)

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
        "comment_count": _pick_comment_count(item),
        "good_comments_share": _pick_good_comments_share(item),
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
    payload.update(price_snapshot)
    return enrich_product_payload_with_compliance(
        payload,
        forbid_types=item.get("forbidTypes") or [],
    )


def upsert_product(db: Session, payload: dict[str, Any]) -> tuple[Product, str]:
    normalized_payload = dict(payload)
    jd_sku_id = str(normalized_payload.get("jd_sku_id") or "").strip()
    if not jd_sku_id:
        raise ValueError("jd_sku_id is empty")

    normalized_payload["jd_sku_id"] = jd_sku_id

    pending_product = _find_pending_product_by_sku(db, jd_sku_id)
    if pending_product:
        for key, value in normalized_payload.items():
            setattr(pending_product, key, value)
        return pending_product, "updated"

    product = db.query(Product).filter(Product.jd_sku_id == jd_sku_id).first()
    if product:
        for key, value in normalized_payload.items():
            setattr(product, key, value)
        return product, "updated"

    product = Product(**normalized_payload)
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

    price_medians = build_category_price_medians(goods)
    inserted = 0
    updated = 0
    rows: list[dict[str, Any]] = []

    for item in goods:
        category_info = item.get("categoryInfo") or {}
        category_name = category_info.get("cid3Name") or category_info.get("cid2Name") or category_info.get("cid1Name") or "unknown"
        merchant_snapshot = build_merchant_snapshot(
            item,
            category_median_price=price_medians.get(category_name),
        )
        upsert_merchant_profile(db, merchant_snapshot)

        material_url = item.get("materialUrl")
        short_url = workflow.build_short_link(material_url) if (with_short_links and material_url) else None
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
        "limit": limit,
        "inserted": inserted,
        "updated": updated,
        "total": len(rows),
        "rows": rows,
    }
