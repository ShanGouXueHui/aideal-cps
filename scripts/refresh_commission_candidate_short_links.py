from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.jd_union_workflow_service import JDUnionWorkflowService

DEFAULT_RULE_PATH = ROOT / "config" / "commission_candidate_short_link_refresh_rules.json"

ROOT.joinpath("run").mkdir(exist_ok=True)
ROOT.joinpath("logs").mkdir(exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_status(path: Path, payload: dict[str, Any]) -> None:
    data = dict(payload)
    data["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def log_event(path: Path, payload: dict[str, Any]) -> None:
    data = dict(payload)
    data["ts"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def select_candidate_ids(candidate_path: Path, allowed_tiers: list[str], limit: int) -> list[int]:
    if limit == 0:
        return []

    payload = load_json(candidate_path)
    rows = payload.get("candidates") or []

    selected: list[int] = []
    seen: set[int] = set()

    for row in rows:
        if str(row.get("tier") or "") not in allowed_tiers:
            continue
        if row.get("has_short_url"):
            continue
        try:
            product_id = int(row.get("id"))
        except Exception:
            continue
        if product_id in seen:
            continue
        seen.add(product_id)
        selected.append(product_id)
        if limit > 0 and len(selected) >= limit:
            break

    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules-path", default=str(DEFAULT_RULE_PATH))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rules = load_json(Path(args.rules_path))
    if not bool(rules.get("enabled", True)):
        print(json.dumps({"job": "refresh_commission_candidate_short_links", "status": "skipped", "reason": "disabled"}, ensure_ascii=False))
        return 0

    candidate_path = ROOT / str(rules.get("input_path", "run/commission_candidate_pool.json"))
    status_path = ROOT / str(rules.get("status_path", "run/commission_candidate_short_link_refresh_status.json"))
    log_path = ROOT / str(rules.get("log_path", "logs/commission_candidate_short_link_refresh.log"))

    if args.limit is None:
        limit = int(rules.get("default_limit", 3000))
    else:
        limit = int(args.limit)
    sleep_seconds = float(rules.get("request_sleep_seconds", 0.25))
    allowed_tiers = [str(x) for x in rules.get("allowed_tiers", ["semi_ready_missing_short_url"])]
    max_failures = int(rules.get("max_failures_before_abort", 100))

    candidate_ids = select_candidate_ids(candidate_path, allowed_tiers, limit)

    status: dict[str, Any] = {
        "job": "refresh_commission_candidate_short_links",
        "status": "running",
        "started_at": now_iso(),
        "rules_path": str(args.rules_path),
        "candidate_path": str(candidate_path),
        "allowed_tiers": allowed_tiers,
        "limit": limit,
        "dry_run": args.dry_run,
        "candidate_ids": len(candidate_ids),
        "attempted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "last_error": None
    }
    write_status(status_path, status)
    log_event(log_path, {"event": "start", **status})

    if not candidate_ids:
        status["status"] = "success"
        status["finished_at"] = now_iso()
        write_status(status_path, status)
        log_event(log_path, {"event": "finish", **status})
        print(json.dumps(status, ensure_ascii=False), flush=True)
        return 0

    workflow = JDUnionWorkflowService()
    db = SessionLocal()

    try:
        for product_id in candidate_ids:
            status["attempted"] += 1
            product = db.query(Product).filter(Product.id == product_id).first()

            if product is None or product.status != "active":
                status["skipped"] += 1
                log_event(log_path, {"event": "skip", "id": product_id, "reason": "missing_or_inactive"})
                continue

            if (product.short_url or "").strip():
                status["skipped"] += 1
                log_event(log_path, {"event": "skip", "id": product_id, "sku": product.jd_sku_id, "reason": "already_has_short_url"})
                continue

            material_id = (product.material_url or product.product_url or "").strip()
            if not material_id:
                status["skipped"] += 1
                log_event(log_path, {"event": "skip", "id": product_id, "sku": product.jd_sku_id, "reason": "missing_material_url"})
                continue

            try:
                short_url = None if args.dry_run else workflow.build_short_link(material_id)
                if short_url:
                    product.short_url = short_url
                    db.commit()
                    status["updated"] += 1
                    log_event(log_path, {"event": "updated", "id": product_id, "sku": product.jd_sku_id, "category": product.category_name})
                elif args.dry_run:
                    status["skipped"] += 1
                    log_event(log_path, {"event": "dry_run", "id": product_id, "sku": product.jd_sku_id})
                else:
                    db.rollback()
                    status["failed"] += 1
                    status["last_error"] = "empty_short_url"
                    log_event(log_path, {"event": "failed", "id": product_id, "sku": product.jd_sku_id, "reason": "empty_short_url"})
            except Exception as exc:
                db.rollback()
                status["failed"] += 1
                status["last_error"] = repr(exc)[:500]
                log_event(log_path, {"event": "failed", "id": product_id, "sku": getattr(product, "jd_sku_id", None), "error": repr(exc)[:500]})

            if status["attempted"] % 25 == 0:
                write_status(status_path, status)

            if status["failed"] >= max_failures:
                status["status"] = "failed"
                status["finished_at"] = now_iso()
                status["stop_reason"] = "max_failures_reached"
                write_status(status_path, status)
                log_event(log_path, {"event": "abort", **status})
                print(json.dumps(status, ensure_ascii=False), flush=True)
                return 1

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        status["status"] = "success"
        status["finished_at"] = now_iso()
        write_status(status_path, status)
        log_event(log_path, {"event": "finish", **status})
        print(json.dumps(status, ensure_ascii=False), flush=True)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
