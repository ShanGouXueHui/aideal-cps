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

DEFAULT_INPUT_PATH = ROOT / "run" / "semi_recommend_pool_candidates.json"
DEFAULT_STATUS_PATH = ROOT / "run" / "semi_short_link_refresh_status.json"
DEFAULT_LOG_PATH = ROOT / "logs" / "semi_short_link_refresh.log"

ROOT.joinpath("run").mkdir(exist_ok=True)
ROOT.joinpath("logs").mkdir(exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_status(path: Path, payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["updated_at"] = now_iso()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def log_event(path: Path, payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["ts"] = now_iso()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_candidate_ids(path: Path) -> list[int]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("candidates") or []
    ids: list[int] = []
    seen: set[int] = set()
    for row in rows:
        if row.get("has_short_url"):
            continue
        try:
            pid = int(row.get("id"))
        except Exception:
            continue
        if pid in seen:
            continue
        seen.add(pid)
        ids.append(pid)
    return ids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-path", default=str(DEFAULT_INPUT_PATH))
    parser.add_argument("--status-path", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--request-sleep-seconds", type=float, default=0.25)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input_path)
    status_path = Path(args.status_path)
    log_path = Path(args.log_path)

    candidate_ids = load_candidate_ids(input_path)
    if args.limit >= 0:
        candidate_ids = candidate_ids[: args.limit]

    status = {
        "job": "refresh_semi_candidate_short_links",
        "status": "running",
        "started_at": now_iso(),
        "input_path": str(input_path),
        "candidate_ids": len(candidate_ids),
        "limit": args.limit,
        "dry_run": args.dry_run,
        "attempted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
    }
    write_status(status_path, status)
    log_event(log_path, {"event": "start", **status})

    if not candidate_ids:
        status.update({"status": "success", "finished_at": now_iso()})
        write_status(status_path, status)
        log_event(log_path, {"event": "finish", **status})
        print(json.dumps(status, ensure_ascii=False), flush=True)
        return 0

    workflow = JDUnionWorkflowService()
    db = SessionLocal()

    try:
        for pid in candidate_ids:
            status["attempted"] += 1
            product = db.query(Product).filter(Product.id == pid).first()

            if product is None or product.status != "active":
                status["skipped"] += 1
                log_event(log_path, {"event": "skip", "id": pid, "reason": "missing_or_inactive"})
                continue

            if (product.short_url or "").strip():
                status["skipped"] += 1
                log_event(log_path, {"event": "skip", "id": pid, "reason": "already_has_short_url"})
                continue

            material_id = (product.material_url or product.product_url or "").strip()
            if not material_id:
                status["skipped"] += 1
                log_event(log_path, {"event": "skip", "id": pid, "sku": product.jd_sku_id, "reason": "missing_material_url"})
                continue

            try:
                if args.dry_run:
                    short_url = None
                else:
                    short_url = workflow.build_short_link(material_id)

                if short_url:
                    product.short_url = short_url
                    db.commit()
                    status["updated"] += 1
                    log_event(log_path, {"event": "updated", "id": pid, "sku": product.jd_sku_id, "category": product.category_name})
                elif args.dry_run:
                    status["skipped"] += 1
                    log_event(log_path, {"event": "dry_run", "id": pid, "sku": product.jd_sku_id})
                else:
                    db.rollback()
                    status["failed"] += 1
                    log_event(log_path, {"event": "failed", "id": pid, "sku": product.jd_sku_id, "reason": "empty_short_url"})
            except Exception as exc:
                db.rollback()
                status["failed"] += 1
                log_event(log_path, {"event": "failed", "id": pid, "sku": getattr(product, "jd_sku_id", None), "error": repr(exc)[:500]})

            if status["attempted"] % 25 == 0:
                write_status(status_path, status)

            if args.request_sleep_seconds > 0:
                time.sleep(args.request_sleep_seconds)

        status.update({"status": "success", "finished_at": now_iso()})
        write_status(status_path, status)
        log_event(log_path, {"event": "finish", **status})
        print(json.dumps(status, ensure_ascii=False), flush=True)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
