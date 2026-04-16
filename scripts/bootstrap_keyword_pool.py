from __future__ import annotations

import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.catalog_refresh_service import _product_payload_from_live_row
from app.services.jd_live_search_service import _normalize_live_item
from app.services.jd_product_sync_service import upsert_product
from app.services.jd_union_client import JDUnionClient, extract_goods_query_items

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "catalog_refresh_rules.json"


def load_rules() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def fetch_task(keyword: str, page_index: int, page_size: int, sort_name: str, sort: str) -> dict:
    client = JDUnionClient()
    response = client.goods_query(
        keyword=keyword,
        page_index=page_index,
        page_size=page_size,
        sort_name=sort_name,
        sort=sort,
    )
    items = extract_goods_query_items(response)
    rows = []
    for item in items:
        api_short = item.get("shortURL") or item.get("shortUrl") or item.get("clickURL")
        row = _normalize_live_item(item, short_url=api_short)
        payload = _product_payload_from_live_row(row, keyword=keyword)
        rows.append(payload)
    return {
        "keyword": keyword,
        "page_index": page_index,
        "count": len(rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-raw-rows", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()

    rules = load_rules()
    bootstrap = rules.get("bootstrap") or {}
    keywords = list(dict.fromkeys(rules.get("keyword_seeds") or []))
    page_size = int(bootstrap.get("page_size", 50))
    pages_per_keyword = int(bootstrap.get("pages_per_keyword", 30))
    db_commit_batch = int(bootstrap.get("db_commit_batch", 200))
    sort_name = rules.get("goods_query_sort_name") or "inOrderCount30DaysSku"
    sort = rules.get("goods_query_sort") or "desc"

    target_raw_rows = int(args.target_raw_rows or bootstrap.get("target_raw_rows") or 0)
    workers = int(args.workers or bootstrap.get("fetch_workers") or 1)
    task_count_needed = max(1, math.ceil(int(target_raw_rows) / page_size))
    tasks = []
    for page_index in range(1, pages_per_keyword + 1):
        for keyword in keywords:
            tasks.append((keyword, page_index))
            if len(tasks) >= task_count_needed:
                break
        if len(tasks) >= task_count_needed:
            break

    print({
        "target_raw_rows": int(target_raw_rows),
        "workers": int(workers),
        "page_size": page_size,
        "pages_per_keyword": pages_per_keyword,
        "keywords": len(keywords),
        "tasks": len(tasks),
        "sort_name": sort_name,
        "sort": sort,
    })

    fetched_rows = 0
    inserted = 0
    updated = 0
    skipped_empty_sku = 0
    seen_in_run = set()
    db = SessionLocal()
    pending = 0

    try:
        with ThreadPoolExecutor(max_workers=int(workers)) as pool:
            futures = {
                pool.submit(fetch_task, keyword, page_index, page_size, sort_name, sort): (keyword, page_index)
                for keyword, page_index in tasks
            }

            for idx, future in enumerate(as_completed(futures), start=1):
                keyword, page_index = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    print({"task_error": {"keyword": keyword, "page_index": page_index, "error": str(e)}})
                    continue

                rows = result.get("rows") or []
                fetched_rows += len(rows)

                for payload in rows:
                    sku = str(payload.get("jd_sku_id") or "").strip()
                    if not sku:
                        skipped_empty_sku += 1
                        continue

                    if sku in seen_in_run:
                        continue
                    seen_in_run.add(sku)

                    product, action = upsert_product(db, payload)
                    pending += 1
                    if action == "inserted":
                        inserted += 1
                    else:
                        updated += 1

                    if pending >= db_commit_batch:
                        db.commit()
                        db.close()
                        db = SessionLocal()
                        pending = 0

                if idx % 50 == 0:
                    print({
                        "tasks_done": idx,
                        "fetched_rows": fetched_rows,
                        "unique_skus_in_run": len(seen_in_run),
                        "inserted": inserted,
                        "updated": updated,
                        "skipped_empty_sku": skipped_empty_sku,
                    })

        if pending > 0:
            db.commit()

        latest_total = db.query(Product).count()
        active_total = db.query(Product).filter(Product.status == "active").count()

        print({
            "done": True,
            "fetched_rows": fetched_rows,
            "unique_skus_in_run": len(seen_in_run),
            "inserted": inserted,
            "updated": updated,
            "skipped_empty_sku": skipped_empty_sku,
            "products_total": latest_total,
            "products_active": active_total,
        })

    finally:
        db.close()


if __name__ == "__main__":
    main()
