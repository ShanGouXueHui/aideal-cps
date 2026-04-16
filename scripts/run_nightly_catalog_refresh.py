from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.catalog_refresh_config_service import load_catalog_refresh_rules
from app.services.catalog_refresh_service import (
    catalog_health_report,
    inactivate_expired_products,
    purge_stale_products,
    refresh_elite_catalog_pages,
    refresh_keyword_catalog_pages,
)
from app.services.jd_exact_price_service import audit_exact_prices
from app.services.jd_union_workflow_service import JDUnionWorkflowService


def _build_short_link_for_material_url(material_url: str) -> tuple[str, str | None]:
    workflow = JDUnionWorkflowService()
    try:
        short_url = workflow.build_short_link(material_url)
        return material_url, short_url
    except Exception:
        return material_url, None


def hydrate_missing_short_urls(*, limit: int, workers: int = 8) -> dict:
    db = SessionLocal()
    try:
        rows = (
            db.query(Product)
            .filter(
                Product.status == "active",
                Product.material_url.isnot(None),
                Product.material_url != "",
            )
            .filter(
                (Product.short_url.is_(None)) | (Product.short_url == "")
            )
            .order_by(
                Product.sales_volume.desc(),
                Product.estimated_commission.desc(),
                Product.id.desc(),
            )
            .limit(limit)
            .all()
        )

        material_to_products: dict[str, list[Product]] = {}
        for row in rows:
            material_to_products.setdefault(str(row.material_url), []).append(row)

        updated = 0
        failed = 0
        results: dict[str, str | None] = {}

        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            future_map = {
                executor.submit(_build_short_link_for_material_url, material_url): material_url
                for material_url in material_to_products.keys()
            }
            for future in as_completed(future_map):
                material_url = future_map[future]
                try:
                    _, short_url = future.result()
                    results[material_url] = short_url
                except Exception:
                    results[material_url] = None

        for material_url, product_rows in material_to_products.items():
            short_url = results.get(material_url)
            if short_url:
                for row in product_rows:
                    row.short_url = short_url
                    if not row.product_url:
                        row.product_url = short_url
                    updated += 1
            else:
                failed += len(product_rows)

        db.commit()
        return {
            "limit": limit,
            "workers": workers,
            "candidate_count": len(rows),
            "unique_material_url_count": len(material_to_products),
            "updated": updated,
            "failed": failed,
        }
    finally:
        db.close()


def run_bootstrap(
    *,
    target_active_with_short_url: int,
    bootstrap_max_rounds: int,
    elite_pages_per_round: int,
    keyword_pages_per_round: int,
    elite_limit: int,
    keyword_limit: int,
    shortlink_hydration_limit: int,
    shortlink_workers: int,
    price_audit_limit: int,
) -> dict:
    rounds = []
    for idx in range(1, bootstrap_max_rounds + 1):
        db = SessionLocal()
        try:
            before_health = catalog_health_report(db)

            elite_result = refresh_elite_catalog_pages(
                db,
                limit=elite_limit,
                page_start=1,
                page_end=elite_pages_per_round,
                with_short_links=False,
            )
            keyword_result = refresh_keyword_catalog_pages(
                db,
                limit=keyword_limit,
                page_start=1,
                page_end=keyword_pages_per_round,
                with_short_links=False,
            )
            inactive_result = inactivate_expired_products(db)
            purge_result = purge_stale_products(db)
            after_ingest_health = catalog_health_report(db)
        finally:
            db.close()

        hydrate_result = hydrate_missing_short_urls(
            limit=shortlink_hydration_limit,
            workers=shortlink_workers,
        )
        price_audit_result = audit_exact_prices(
            limit=price_audit_limit,
            workers=shortlink_workers,
            batch_size=20,
        )

        db = SessionLocal()
        try:
            final_health = catalog_health_report(db)
        finally:
            db.close()

        rounds.append(
            {
                "round": idx,
                "before_health": before_health,
                "elite_refresh": elite_result,
                "keyword_refresh": keyword_result,
                "inactive": inactive_result,
                "purge": purge_result,
                "after_ingest_health": after_ingest_health,
                "shortlink_hydration": hydrate_result,
                "price_audit": price_audit_result,
                "final_health": final_health,
            }
        )

        if int(final_health.get("products_active_with_short_url", 0)) >= target_active_with_short_url:
            break

    return {
        "mode": "bootstrap",
        "target_active_with_short_url": target_active_with_short_url,
        "bootstrap_max_rounds": bootstrap_max_rounds,
        "elite_pages_per_round": elite_pages_per_round,
        "keyword_pages_per_round": keyword_pages_per_round,
        "elite_limit": elite_limit,
        "keyword_limit": keyword_limit,
        "shortlink_hydration_limit": shortlink_hydration_limit,
        "shortlink_workers": shortlink_workers,
        "price_audit_limit": price_audit_limit,
        "rounds": rounds,
        "final_health": rounds[-1]["final_health"] if rounds else {},
    }


def run_daily() -> dict:
    rules = load_catalog_refresh_rules()

    elite_pages_per_run = int(rules.get("elite_pages_per_run", 3400))
    keyword_pages_per_run = int(rules.get("keyword_pages_per_run", 2))
    elite_limit = int(rules.get("elite_sync_limit", 30))
    keyword_limit = int(rules.get("keyword_sync_limit", 24))
    shortlink_hydration_limit = int(rules.get("shortlink_hydration_limit_per_run", 5000))
    shortlink_workers = int(rules.get("shortlink_workers", 8))
    price_audit_limit = int(rules.get("price_audit_limit_per_run", 5000))

    db = SessionLocal()
    try:
        elite_result = refresh_elite_catalog_pages(
            db,
            limit=elite_limit,
            page_start=1,
            page_end=elite_pages_per_run,
            with_short_links=False,
        )
        keyword_result = refresh_keyword_catalog_pages(
            db,
            limit=keyword_limit,
            page_start=1,
            page_end=keyword_pages_per_run,
            with_short_links=False,
        )
        inactive_result = inactivate_expired_products(db)
        purge_result = purge_stale_products(db)
        after_ingest_health = catalog_health_report(db)
    finally:
        db.close()

    hydrate_result = hydrate_missing_short_urls(
        limit=shortlink_hydration_limit,
        workers=shortlink_workers,
    )
    price_audit_result = audit_exact_prices(
        limit=price_audit_limit,
        workers=shortlink_workers,
        batch_size=20,
    )

    db = SessionLocal()
    try:
        final_health = catalog_health_report(db)
    finally:
        db.close()

    return {
        "mode": "daily",
        "elite_pages_per_run": elite_pages_per_run,
        "keyword_pages_per_run": keyword_pages_per_run,
        "elite_limit": elite_limit,
        "keyword_limit": keyword_limit,
        "shortlink_hydration_limit_per_run": shortlink_hydration_limit,
        "shortlink_workers": shortlink_workers,
        "price_audit_limit_per_run": price_audit_limit,
        "elite_refresh": elite_result,
        "keyword_refresh": keyword_result,
        "inactive": inactive_result,
        "purge": purge_result,
        "after_ingest_health": after_ingest_health,
        "shortlink_hydration": hydrate_result,
        "price_audit": price_audit_result,
        "final_health": final_health,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--target-active-with-short-url", type=int, default=500)
    parser.add_argument("--bootstrap-max-rounds", type=int, default=5)
    parser.add_argument("--elite-pages-per-round", type=int, default=20)
    parser.add_argument("--keyword-pages-per-round", type=int, default=1)
    parser.add_argument("--elite-limit", type=int, default=30)
    parser.add_argument("--keyword-limit", type=int, default=24)
    parser.add_argument("--shortlink-hydration-limit", type=int, default=500)
    parser.add_argument("--shortlink-workers", type=int, default=8)
    parser.add_argument("--price-audit-limit", type=int, default=500)
    args = parser.parse_args()

    if args.bootstrap:
        result = run_bootstrap(
            target_active_with_short_url=args.target_active_with_short_url,
            bootstrap_max_rounds=args.bootstrap_max_rounds,
            elite_pages_per_round=args.elite_pages_per_round,
            keyword_pages_per_round=args.keyword_pages_per_round,
            elite_limit=args.elite_limit,
            keyword_limit=args.keyword_limit,
            shortlink_hydration_limit=args.shortlink_hydration_limit,
            shortlink_workers=args.shortlink_workers,
            price_audit_limit=args.price_audit_limit,
        )
    else:
        result = run_daily()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
