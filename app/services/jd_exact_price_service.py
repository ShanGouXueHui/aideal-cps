from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.jd_product_sync_service import _price_snapshot_from_price_info
from app.services.jd_union_client import JDUnionClient, extract_goods_query_items


def _to_decimal(value: Any) -> Decimal:
    try:
        if value is None or str(value).strip() == "":
            return Decimal("0")
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _to_float(value: Any) -> float:
    try:
        if value is None or str(value).strip() == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _norm_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"https?://", "", text)
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text)
    return text


def _tokens(value: Any) -> set[str]:
    text = str(value or "").lower()
    chunks = re.findall(r"[0-9a-zA-Z]+|[\u4e00-\u9fff]{2,}", text)
    return {x for x in chunks if len(x) >= 2}


def _material_signature(value: Any) -> str:
    text = str(value or "").strip()
    m = re.search(r"/detail/([^/?#]+)\.html", text)
    if not m:
        m = re.search(r"detail/([^/?#]+)\.html", text)
    if not m:
        return ""
    token = m.group(1)
    if "_" in token:
        return token.split("_")[-1]
    return token


def _item_ids(item: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in ("skuId", "sku_id", "wareId", "spuid", "itemId", "oriItemId", "callerItemId"):
        value = item.get(key)
        if value is not None and str(value).strip():
            out.add(str(value).strip())
    return out


def _title_similarity(a: Any, b: Any) -> float:
    na = _norm_text(a)
    nb = _norm_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return min(len(na), len(nb)) / max(len(na), len(nb))

    ta = _tokens(a)
    tb = _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _candidate_score(product: Product, item: dict[str, Any]) -> tuple[int, float]:
    sku_id = str(getattr(product, "jd_sku_id", "") or "").strip()
    product_title = str(getattr(product, "title", "") or "")
    product_sig = _material_signature(getattr(product, "material_url", None))
    item_sig = _material_signature(item.get("materialUrl") or item.get("material_url"))
    item_title = item.get("skuName") or item.get("title") or ""

    score = 0

    if sku_id and sku_id in _item_ids(item):
        score += 120

    if product_sig and item_sig and product_sig == item_sig:
        score += 90

    title_sim = _title_similarity(product_title, item_title)
    if title_sim >= 0.98:
        score += 70
    elif title_sim >= 0.86:
        score += 45
    elif title_sim >= 0.72:
        score += 25

    # Prefer items that actually expose price information.
    price_info = item.get("priceInfo") or {}
    purchase_price_info = item.get("purchasePriceInfo") or {}
    snapshot = _price_snapshot_from_price_info(price_info, purchase_price_info)
    purchase = _to_float(snapshot.get("purchase_price"))
    basis = _to_float(snapshot.get("basis_price"))
    if purchase > 0 and basis > 0:
        score += 10
    if basis > purchase > 0:
        score += 10

    return score, title_sim


def _select_best_goods_query_item(product: Product, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: tuple[int, float, dict[str, Any]] | None = None
    for item in items:
        score, title_sim = _candidate_score(product, item)
        if best is None or (score, title_sim) > (best[0], best[1]):
            best = (score, title_sim, item)

    if not best:
        return None

    score, title_sim, item = best
    sku_id = str(getattr(product, "jd_sku_id", "") or "").strip()
    numeric_or_material_match = bool(sku_id and sku_id in _item_ids(item)) or (
        _material_signature(getattr(product, "material_url", None))
        and _material_signature(getattr(product, "material_url", None)) == _material_signature(item.get("materialUrl") or item.get("material_url"))
    )

    # Strict enough to avoid updating a different package/specification.
    if numeric_or_material_match and score >= 100:
        return item
    if title_sim >= 0.92 and score >= 85:
        return item
    return None


def _apply_goods_query_item_to_product(product: Product, item: dict[str, Any]) -> dict[str, Any]:
    price_info = item.get("priceInfo") or {}
    purchase_price_info = item.get("purchasePriceInfo") or {}
    snapshot = _price_snapshot_from_price_info(price_info, purchase_price_info)

    price = _to_decimal(price_info.get("price") or price_info.get("lowestPrice") or snapshot.get("basis_price"))
    coupon_price = _to_decimal(
        price_info.get("lowestCouponPrice")
        or snapshot.get("purchase_price")
        or price_info.get("lowestPrice")
        or price_info.get("price")
    )

    if price > 0:
        product.price = price
    if coupon_price > 0:
        product.coupon_price = coupon_price

    for key, value in snapshot.items():
        setattr(product, key, value)

    material_url = item.get("materialUrl") or item.get("material_url")
    if material_url:
        product.material_url = material_url
        if not product.product_url:
            product.product_url = material_url

    image_info = item.get("imageInfo") or {}
    image_url = None
    if image_info.get("whiteImage"):
        image_url = image_info.get("whiteImage")
    else:
        image_list = image_info.get("imageList") or []
        if isinstance(image_list, list) and image_list:
            image_url = image_list[0].get("url")
        elif isinstance(image_list, dict):
            image_url = image_list.get("url")
    if image_url:
        product.image_url = image_url

    product.last_sync_at = datetime.now(timezone.utc)

    compliance_level = str(getattr(product, "compliance_level", "normal") or "normal").strip()
    if compliance_level == "normal":
        product.allow_proactive_push = bool(
            getattr(product, "is_exact_discount", False)
            and _to_float(getattr(product, "purchase_price", None)) > 0
            and _to_float(getattr(product, "basis_price", None)) > _to_float(getattr(product, "purchase_price", None))
        )

    return {
        "fresh": bool(snapshot.get("price_verified_at")),
        "official_price": _to_decimal(snapshot.get("basis_price")),
        "discount_price": _to_decimal(snapshot.get("purchase_price")),
        "saved": max(_to_decimal(snapshot.get("basis_price")) - _to_decimal(snapshot.get("purchase_price")), Decimal("0")),
    }


def refresh_single_product_exact_price(db, product: Product) -> Product:
    title = str(getattr(product, "title", "") or "").strip()
    if not title:
        return product

    try:
        client = JDUnionClient()
        response = client.goods_query(keyword=title, page_index=1, page_size=10)
        items = extract_goods_query_items(response)
        item = _select_best_goods_query_item(product, items)
        if not item:
            return product

        _apply_goods_query_item_to_product(product, item)

        db.commit()
        db.refresh(product)
    except Exception:
        db.rollback()

    return product


def is_discount_eligible_product(product: Product) -> bool:
    try:
        purchase = _to_decimal(getattr(product, "purchase_price", None) or getattr(product, "coupon_price", 0))
        basis = _to_decimal(getattr(product, "basis_price", None) or getattr(product, "price", 0))
        return basis > 0 and purchase > 0 and purchase < basis
    except Exception:
        return False


def audit_exact_prices(
    *,
    limit: int = 5000,
    workers: int = 1,
    batch_size: int = 20,
) -> dict[str, Any]:
    """Sequential audit using the same goods.query exact-match path as production refresh.

    Kept intentionally simple: no legacy price endpoint branch, no parallel mutation.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(Product)
            .filter(Product.status == "active")
            .filter(Product.title.isnot(None), Product.title != "")
            .order_by(
                Product.allow_proactive_push.desc(),
                Product.sales_volume.desc(),
                Product.estimated_commission.desc(),
                Product.id.desc(),
            )
            .limit(limit)
            .all()
        )

        refreshed = 0
        verified_discount = 0
        verified_not_discount = 0
        missing = 0

        for row in rows:
            before = getattr(row, "price_verified_at", None)
            refresh_single_product_exact_price(db, row)
            after = getattr(row, "price_verified_at", None)

            if after and after != before:
                refreshed += 1
                if is_discount_eligible_product(row):
                    verified_discount += 1
                else:
                    verified_not_discount += 1
            else:
                missing += 1

        return {
            "limit": limit,
            "candidate_count": len(rows),
            "refreshed": refreshed,
            "verified_discount": verified_discount,
            "verified_not_discount": verified_not_discount,
            "missing": missing,
            "source": "goods_query_exact_match",
        }
    finally:
        db.close()
