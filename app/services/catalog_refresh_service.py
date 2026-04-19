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
from app.services.proactive_whitelist_refresh_service import refresh_proactive_recommend_whitelist


def _product_payload_from_live_row(row: dict[str, Any], *, keyword: str, source_profile: str = "") -> dict[str, Any]:
    allowed_keys = set(Product.__table__.columns.keys())

    ai_tags = f"关键词池:{keyword}"
    if source_profile:
        ai_tags = f"{ai_tags}|榜单:{source_profile}"

    payload = {
        "jd_sku_id": row.get("jd_sku_id"),
        "title": row.get("title"),
        "description": row.get("description"),
        "image_url": row.get("image_url"),
        "product_url": row.get("product_url") or row.get("short_url"),
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
        "ai_tags": ai_tags,
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


def _catalog_sort_profiles(rules: dict[str, Any], *, default_limit: int) -> list[dict[str, Any]]:
    raw_profiles = rules.get("keyword_sort_profiles")
    if not isinstance(raw_profiles, list) or not raw_profiles:
        return [
            {
                "name": "default",
                "sort_name": rules.get("goods_query_sort_name"),
                "sort": rules.get("goods_query_sort", "desc"),
                "limit": default_limit,
            }
        ]

    profiles: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for item in raw_profiles:
        if not isinstance(item, dict):
            continue

        sort_name = item.get("sort_name") or item.get("sortName")
        sort = item.get("sort") or rules.get("goods_query_sort") or "desc"
        extra_goods_req = item.get("extra_goods_req") if isinstance(item.get("extra_goods_req"), dict) else None

        try:
            limit = int(item.get("limit") or item.get("page_size") or default_limit)
        except Exception:
            limit = default_limit

        limit = max(1, min(limit, 50))
        name = str(item.get("name") or sort_name or f"profile_{len(profiles) + 1}").strip()

        key = (str(sort_name or ""), str(sort or ""), str(extra_goods_req or ""))
        if key in seen:
            continue
        seen.add(key)

        profiles.append(
            {
                "name": name,
                "sort_name": sort_name,
                "sort": sort,
                "limit": limit,
                "extra_goods_req": extra_goods_req,
            }
        )

    return profiles or [
        {
            "name": "default",
            "sort_name": rules.get("goods_query_sort_name"),
            "sort": rules.get("goods_query_sort", "desc"),
            "limit": default_limit,
        }
    ]


def refresh_elite_catalogs(
    db: Session,
    *,
    elite_ids: list[int] | None = None,
    limit: int | None = None,
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
            page_index=1,
            page_size=limit,
            with_short_links=True,
        )
        total_inserted += int(result.get("inserted", 0))
        total_updated += int(result.get("updated", 0))
        total_rows += int(result.get("total", 0))
        results.append(result)

    return {
        "elite_ids": elite_ids,
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
    jd_client: JDUnionClient | None = None,
) -> dict[str, Any]:
    rules = load_catalog_refresh_rules()
    limit = int(limit or rules.get("keyword_sync_limit", 12))
    client = jd_client or JDUnionClient()
    profiles = _catalog_sort_profiles(rules, default_limit=limit)

    inserted = 0
    updated = 0
    rows: list[dict[str, Any]] = []
    seen_jd_sku_ids: set[str] = set()
    profile_results: list[dict[str, Any]] = []

    for profile in profiles:
        profile_name = str(profile.get("name") or "default")
        profile_limit = int(profile.get("limit") or limit)
        profile_inserted = 0
        profile_updated = 0
        profile_rows = 0

        try:
            response = client.goods_query(
                keyword=keyword,
                page_index=1,
                page_size=profile_limit,
                sort_name=profile.get("sort_name"),
                sort=profile.get("sort"),
                extra_goods_req=profile.get("extra_goods_req"),
            )
            items = extract_goods_query_items(response)
        except Exception as exc:
            profile_results.append(
                {
                    "profile": profile_name,
                    "sort_name": profile.get("sort_name"),
                    "sort": profile.get("sort"),
                    "limit": profile_limit,
                    "inserted": 0,
                    "updated": 0,
                    "total": 0,
                    "error": str(exc),
                }
            )
            continue

        for item in items[:profile_limit]:
            material_url = _pick_material_url(item)
            short_url = _build_short_link(client, material_url)
            live_row = _normalize_live_item(item, short_url=short_url)
            payload = _product_payload_from_live_row(
                live_row,
                keyword=keyword,
                source_profile=profile_name,
            )

            jd_sku_id = str(payload.get("jd_sku_id") or "").strip()
            if not jd_sku_id:
                continue
            if jd_sku_id in seen_jd_sku_ids:
                continue
            seen_jd_sku_ids.add(jd_sku_id)
            payload["jd_sku_id"] = jd_sku_id

            product, action = upsert_product(db, payload)
            if action == "inserted":
                inserted += 1
                profile_inserted += 1
            else:
                updated += 1
                profile_updated += 1

            profile_rows += 1
            rows.append(
                {
                    "jd_sku_id": product.jd_sku_id,
                    "title": product.title,
                    "short_url": product.short_url,
                    "keyword": keyword,
                    "source_profile": profile_name,
                    "compliance_level": getattr(product, "compliance_level", None),
                    "action": action,
                }
            )

        profile_results.append(
            {
                "profile": profile_name,
                "sort_name": profile.get("sort_name"),
                "sort": profile.get("sort"),
                "limit": profile_limit,
                "inserted": profile_inserted,
                "updated": profile_updated,
                "total": profile_rows,
            }
        )

    db.commit()
    return {
        "keyword": keyword,
        "profiles": profile_results,
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
    jd_client: JDUnionClient | None = None,
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
            jd_client=jd_client,
        )
        total_inserted += int(result.get("inserted", 0))
        total_updated += int(result.get("updated", 0))
        total_rows += int(result.get("total", 0))
        results.append(result)

    return {
        "keywords": keywords,
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
    expire_hours = int(expire_hours or rules.get("expire_hours", 72))
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
    purge_hours = int(purge_hours or rules.get("purge_hours", 240))
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
        "candidate_count": len(rows),
    }


def run_nightly_catalog_refresh(db: Session) -> dict[str, Any]:
    elite_result = refresh_elite_catalogs(db)
    keyword_result = refresh_keyword_catalogs(db)
    inactive_result = inactivate_expired_products(db)
    purge_result = purge_stale_products(db)

    try:
        whitelist_result = refresh_proactive_recommend_whitelist(db)
    except Exception as exc:
        whitelist_result = {
            "status": "failed",
            "error": str(exc),
        }

    return {
        "elite_refresh": elite_result,
        "keyword_refresh": keyword_result,
        "inactive_cleanup": inactive_result,
        "purge_cleanup": purge_result,
        "proactive_whitelist_refresh": whitelist_result,
    }
