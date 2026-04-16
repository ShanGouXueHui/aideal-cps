from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.click_log import ClickLog
from app.models.partner_share_asset import PartnerShareAsset
from app.models.partner_share_click import PartnerShareClick
from app.models.product import Product
from app.services.catalog_refresh_config_service import load_catalog_refresh_rules
from app.services.jd_live_search_service import _build_short_link, _normalize_live_item, _pick_material_url
from app.services.jd_product_sync_service import sync_jd_products, upsert_product
from app.services.jd_union_client import JDUnionClient, extract_goods_query_items


def _product_payload_from_live_row(row: dict[str, Any], *, keyword: str) -> dict[str, Any]:
    allowed_keys = set(Product.__table__.columns.keys())

    payload = {
        "jd_sku_id": row.get("jd_sku_id"),
        "title": row.get("title"),
        "description": row.get("description"),
        "image_url": row.get("image_url"),
        "product_url": row.get("product_url") or row.get("short_url") or row.get("material_url"),
        "material_url": row.get("material_url"),
        "short_url": row.get("short_url"),
        "category_name": row.get("category_name"),
        "shop_name": row.get("shop_name"),
        "shop_id": row.get("shop_id"),
        "price": row.get("price"),
        "coupon_price": row.get("coupon_price"),
        "commission_rate": row.get("commission_rate"),
        "estimated_commission": row.get("estimated_commission"),
        "sales_volume": row.get("sales_volume"),
        "coupon_info": row.get("coupon_info"),
        "ai_reason": row.get("reason"),
        "ai_tags": f"关键词池:{keyword}",
        "elite_id": row.get("elite_id"),
        "elite_name": row.get("elite_name") or "关键词池",
        "owner": row.get("owner"),
        "merchant_health_score": row.get("merchant_health_score"),
        "merchant_risk_flags": row.get("merchant_risk_flags"),
        "merchant_recommendable": row.get("merchant_recommendable", True),
        "status": "active",
        "last_sync_at": datetime.now(timezone.utc),
        "compliance_level": row.get("compliance_level"),
        "allow_proactive_push": row.get("allow_proactive_push"),
        "allow_partner_share": row.get("allow_partner_share"),
        "compliance_notes": row.get("compliance_notes"),
    }

    return {k: v for k, v in payload.items() if k in allowed_keys}


def refresh_elite_catalogs(
    db: Session,
    *,
    elite_ids: list[int] | None = None,
    limit: int | None = None,
    page_index: int = 1,
    with_short_links: bool = True,
) -> dict[str, Any]:
    rules = load_catalog_refresh_rules()
    elite_ids = elite_ids or list(rules.get("elite_ids", []))
    limit = int(limit or rules.get("elite_sync_limit", 20))

    results = []
    total_inserted = 0
    total_updated = 0
    total_rows = 0

    for elite_id in elite_ids:
        result = sync_jd_products(
            db,
            elite_id=int(elite_id),
            limit=limit,
            page_index=page_index,
            page_size=limit,
            with_short_links=with_short_links,
        )
        total_inserted += int(result.get("inserted", 0))
        total_updated += int(result.get("updated", 0))
        total_rows += int(result.get("total", 0))
        results.append(result)

    return {
        "elite_ids": elite_ids,
        "page_index": page_index,
        "with_short_links": with_short_links,
        "inserted": total_inserted,
        "updated": total_updated,
        "total": total_rows,
        "results": results,
    }


def refresh_elite_catalog_pages(
    db: Session,
    *,
    elite_ids: list[int] | None = None,
    limit: int | None = None,
    page_start: int = 1,
    page_end: int = 1,
    with_short_links: bool = True,
) -> dict[str, Any]:
    results = []
    total_inserted = 0
    total_updated = 0
    total_rows = 0

    for page_index in range(page_start, page_end + 1):
        result = refresh_elite_catalogs(
            db,
            elite_ids=elite_ids,
            limit=limit,
            page_index=page_index,
            with_short_links=with_short_links,
        )
        total_inserted += int(result.get("inserted", 0))
        total_updated += int(result.get("updated", 0))
        total_rows += int(result.get("total", 0))
        results.append(result)

    return {
        "page_start": page_start,
        "page_end": page_end,
        "with_short_links": with_short_links,
        "inserted": total_inserted,
        "updated": total_updated,
        "total": total_rows,
        "results": results,
    }


def refresh_keyword_catalog(
    db: Session,
    *,
    keyword: str,
    limit: int | None = None,
    page_index: int = 1,
    jd_client: JDUnionClient | None = None,
    with_short_links: bool = True,
) -> dict[str, Any]:
    rules = load_catalog_refresh_rules()
    limit = int(limit or rules.get("keyword_sync_limit", 12))
    client = jd_client or JDUnionClient()

    response = client.goods_query(
        keyword=keyword,
        page_index=page_index,
        page_size=limit,
        sort_name=rules.get("goods_query_sort_name"),
        sort=rules.get("goods_query_sort"),
    )
    items = extract_goods_query_items(response)

    inserted = 0
    updated = 0
    rows: list[dict[str, Any]] = []

    for item in items[:limit]:
        material_url = _pick_material_url(item)
        short_url = _build_short_link(client, material_url) if (with_short_links and material_url) else None
        live_row = _normalize_live_item(item, short_url=short_url)
        payload = _product_payload_from_live_row(live_row, keyword=keyword)

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
                "keyword": keyword,
                "page_index": page_index,
                "with_short_links": with_short_links,
                "compliance_level": getattr(product, "compliance_level", None),
                "action": action,
            }
        )

    db.commit()
    return {
        "keyword": keyword,
        "page_index": page_index,
        "with_short_links": with_short_links,
        "inserted": inserted,
        "updated": updated,
        "total": len(rows),
        "rows": rows,
    }


def refresh_keyword_catalogs(
    db: Session,
    *,
    keywords: list[str] | None = None,
    limit: int | None = None,
    page_index: int = 1,
    jd_client: JDUnionClient | None = None,
    with_short_links: bool = True,
) -> dict[str, Any]:
    rules = load_catalog_refresh_rules()
    keywords = keywords or list(rules.get("keyword_seeds", []))
    limit = int(limit or rules.get("keyword_sync_limit", 12))

    results = []
    total_inserted = 0
    total_updated = 0
    total_rows = 0

    for keyword in keywords:
        result = refresh_keyword_catalog(
            db,
            keyword=keyword,
            limit=limit,
            page_index=page_index,
            jd_client=jd_client,
            with_short_links=with_short_links,
        )
        total_inserted += int(result.get("inserted", 0))
        total_updated += int(result.get("updated", 0))
        total_rows += int(result.get("total", 0))
        results.append(result)

    return {
        "keywords": keywords,
        "page_index": page_index,
        "with_short_links": with_short_links,
        "inserted": total_inserted,
        "updated": total_updated,
        "total": total_rows,
        "results": results,
    }


def refresh_keyword_catalog_pages(
    db: Session,
    *,
    keywords: list[str] | None = None,
    limit: int | None = None,
    page_start: int = 1,
    page_end: int = 1,
    with_short_links: bool = True,
) -> dict[str, Any]:
    results = []
    total_inserted = 0
    total_updated = 0
    total_rows = 0

    for page_index in range(page_start, page_end + 1):
        result = refresh_keyword_catalogs(
            db,
            keywords=keywords,
            limit=limit,
            page_index=page_index,
            with_short_links=with_short_links,
        )
        total_inserted += int(result.get("inserted", 0))
        total_updated += int(result.get("updated", 0))
        total_rows += int(result.get("total", 0))
        results.append(result)

    return {
        "page_start": page_start,
        "page_end": page_end,
        "with_short_links": with_short_links,
        "inserted": total_inserted,
        "updated": total_updated,
        "total": total_rows,
        "results": results,
    }


def inactivate_expired_products(
    db: Session,
    *,
    expire_hours: int | None = None,
) -> dict[str, Any]:
    rules = load_catalog_refresh_rules()
    expire_hours = int(expire_hours or rules.get("expire_hours", 24))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=expire_hours)

    rows = (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.last_sync_at.isnot(None),
            Product.last_sync_at < cutoff,
        )
        .all()
    )

    for row in rows:
        row.status = "inactive"

    db.commit()
    return {
        "expire_hours": expire_hours,
        "inactive_count": len(rows),
    }


def _has_downstream_refs(db: Session, product_id: int) -> bool:
    if db.query(ClickLog.id).filter(ClickLog.product_id == product_id).first():
        return True
    if db.query(PartnerShareAsset.id).filter(PartnerShareAsset.product_id == product_id).first():
        return True
    if db.query(PartnerShareClick.id).filter(PartnerShareClick.product_id == product_id).first():
        return True
    return False


def purge_stale_products(
    db: Session,
    *,
    purge_hours: int | None = None,
) -> dict[str, Any]:
    rules = load_catalog_refresh_rules()
    purge_hours = int(purge_hours or rules.get("purge_hours", 72))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=purge_hours)

    rows = (
        db.query(Product)
        .filter(
            Product.status == "inactive",
            Product.last_sync_at.isnot(None),
            Product.last_sync_at < cutoff,
        )
        .all()
    )

    purged = 0
    skipped = 0
    for row in rows:
        if _has_downstream_refs(db, row.id):
            skipped += 1
            continue
        db.delete(row)
        purged += 1

    db.commit()
    return {
        "purge_hours": purge_hours,
        "purged_count": purged,
        "skipped_with_refs": skipped,
    }


def catalog_health_report(
    db: Session,
    *,
    expire_hours: int | None = None,
) -> dict[str, Any]:
    rules = load_catalog_refresh_rules()
    expire_hours = int(expire_hours or rules.get("expire_hours", 24))
    now = datetime.now(timezone.utc)
    expire_cutoff = now - timedelta(hours=expire_hours)
    recent_24h = now - timedelta(hours=24)

    total = db.query(Product).count()
    active = db.query(Product).filter(Product.status == "active").count()
    inactive = db.query(Product).filter(Product.status == "inactive").count()
    active_with_short_url = db.query(Product).filter(
        Product.status == "active",
        Product.short_url.isnot(None),
        Product.short_url != "",
    ).count()
    active_without_short_url = db.query(Product).filter(
        Product.status == "active",
    ).filter(
        (Product.short_url.is_(None)) | (Product.short_url == "")
    ).count()
    active_recent_24h = db.query(Product).filter(
        Product.status == "active",
        Product.last_sync_at.isnot(None),
        Product.last_sync_at >= recent_24h,
    ).count()
    active_stale_over_expire = db.query(Product).filter(
        Product.status == "active",
        Product.last_sync_at.isnot(None),
        Product.last_sync_at < expire_cutoff,
    ).count()

    return {
        "products_total": total,
        "products_active": active,
        "products_inactive": inactive,
        "products_active_with_short_url": active_with_short_url,
        "products_active_without_short_url": active_without_short_url,
        "products_active_recent_24h": active_recent_24h,
        "products_active_stale_over_expire": active_stale_over_expire,
    }
