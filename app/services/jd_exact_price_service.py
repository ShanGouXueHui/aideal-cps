from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.jd_union_client import JDUnionClient


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _extract_promotiongoodsinfo_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    outer = response.get("jd_union_open_goods_promotiongoodsinfo_query_responce", {}) or {}

    payload = (
        outer.get("result")
        or outer.get("queryResult")
        or outer.get("data")
        or outer.get("getpromotiongoodsinfo_result")
        or {}
    )

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}

    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ["data", "result", "list", "rows"]:
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for subkey in ["list", "rows", "data", "result"]:
                    subvalue = value.get(subkey)
                    if isinstance(subvalue, list):
                        return subvalue

    return []


def _fetch_promotiongoodsinfo_batch(sku_ids: list[str]) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    client = JDUnionClient()
    response = client.request(
        "jd.union.open.goods.promotiongoodsinfo.query",
        {
            "skuIds": ",".join([str(x) for x in sku_ids if str(x).strip()]),
        },
    )
    return sku_ids, _extract_promotiongoodsinfo_items(response), response


def _item_sku_id(item: dict[str, Any]) -> str:
    return str(
        item.get("skuId")
        or item.get("sku_id")
        or item.get("wareId")
        or item.get("itemId")
        or ""
    ).strip()


def _extract_price_snapshot_from_promotiongoodsinfo(item: dict[str, Any], product: Product) -> dict[str, Any]:
    official_price = _to_decimal(
        item.get("unitPrice")
        or item.get("price")
        or item.get("jdPrice")
    )
    discount_price = _to_decimal(getattr(product, "coupon_price", 0) or getattr(product, "price", 0))

    if official_price <= 0 or discount_price <= 0:
        return {
            "fresh": False,
            "official_price": Decimal("0"),
            "discount_price": Decimal("0"),
            "saved": Decimal("0"),
        }

    saved = official_price - discount_price if official_price > discount_price else Decimal("0")
    return {
        "fresh": True,
        "official_price": official_price,
        "discount_price": discount_price,
        "saved": saved,
    }


def _apply_promotiongoodsinfo_to_product(product: Product, item: dict[str, Any]) -> dict[str, Any]:
    snapshot = _extract_price_snapshot_from_promotiongoodsinfo(item, product)

    material_url = item.get("materialUrl") or item.get("material_url")
    if material_url:
        product.material_url = material_url
        if not product.product_url:
            product.product_url = material_url

    image_url = item.get("imgUrl") or item.get("imageUrl")
    if image_url:
        product.image_url = image_url

    if snapshot["fresh"]:
        product.price = snapshot["official_price"]

    product.last_sync_at = datetime.now(timezone.utc)
    return snapshot


def is_discount_eligible_product(product: Product) -> bool:
    try:
        price = _to_decimal(getattr(product, "price", 0))
        coupon_price = _to_decimal(getattr(product, "coupon_price", 0))
        return price > 0 and coupon_price > 0 and coupon_price < price
    except Exception:
        return False


def refresh_single_product_exact_price(db, product: Product) -> Product:
    sku_id = str(getattr(product, "jd_sku_id", "") or "").strip()
    if not sku_id:
        return product

    try:
        _, items, _ = _fetch_promotiongoodsinfo_batch([sku_id])
        item_map = {_item_sku_id(item): item for item in items if _item_sku_id(item)}
        item = item_map.get(sku_id)
        if not item:
            return product

        snapshot = _apply_promotiongoodsinfo_to_product(product, item)

        compliance_level = str(getattr(product, "compliance_level", "normal") or "normal").strip()
        if compliance_level == "normal":
            product.allow_proactive_push = bool(
                snapshot["fresh"] and snapshot["discount_price"] < snapshot["official_price"]
            )

        db.commit()
        db.refresh(product)
    except Exception:
        db.rollback()

    return product


def audit_exact_prices(
    *,
    limit: int = 5000,
    workers: int = 8,
    batch_size: int = 20,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Product)
            .filter(Product.status == "active")
            .filter(Product.jd_sku_id.isnot(None), Product.jd_sku_id != "")
            .order_by(
                Product.allow_proactive_push.desc(),
                Product.sales_volume.desc(),
                Product.estimated_commission.desc(),
                Product.id.desc(),
            )
            .limit(limit)
            .all()
        )

        sku_to_products: dict[str, list[Product]] = {}
        for row in rows:
            sku_to_products.setdefault(str(row.jd_sku_id), []).append(row)

        sku_ids = list(sku_to_products.keys())
        batches = _chunked(sku_ids, max(1, batch_size))

        fetched_items: dict[str, dict[str, Any]] = {}
        failed_batches = 0
        sample_errors: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            future_map = {
                executor.submit(_fetch_promotiongoodsinfo_batch, batch): batch
                for batch in batches
            }
            for future in as_completed(future_map):
                batch = future_map[future]
                try:
                    _, items, raw_response = future.result()
                    for item in items:
                        sku_id = _item_sku_id(item)
                        if sku_id:
                            fetched_items[sku_id] = item
                    if not items and len(sample_errors) < 3:
                        sample_errors.append({
                            "batch": batch,
                            "raw_response": raw_response,
                        })
                except Exception as e:
                    failed_batches += 1
                    if len(sample_errors) < 3:
                        sample_errors.append({
                            "batch": batch,
                            "exception": repr(e),
                        })

        verified_discount = 0
        verified_not_discount = 0
        missing = 0

        for sku_id, product_rows in sku_to_products.items():
            item = fetched_items.get(sku_id)
            if not item:
                missing += len(product_rows)
                continue

            for row in product_rows:
                snapshot = _apply_promotiongoodsinfo_to_product(row, item)

                compliance_level = str(getattr(row, "compliance_level", "normal") or "normal").strip()
                if compliance_level == "normal":
                    row.allow_proactive_push = bool(
                        snapshot["fresh"] and snapshot["discount_price"] < snapshot["official_price"]
                    )

                if snapshot["fresh"] and snapshot["discount_price"] < snapshot["official_price"]:
                    verified_discount += 1
                else:
                    verified_not_discount += 1

        db.commit()

        return {
            "limit": limit,
            "workers": workers,
            "batch_size": batch_size,
            "candidate_count": len(rows),
            "unique_sku_count": len(sku_ids),
            "fetched_item_count": len(fetched_items),
            "failed_batches": failed_batches,
            "verified_discount": verified_discount,
            "verified_not_discount": verified_not_discount,
            "missing": missing,
            "sample_errors": sample_errors,
        }
    finally:
        db.close()
