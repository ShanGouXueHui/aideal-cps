#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func

from app.core.db import SessionLocal
from app.models.product import Product

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = ROOT / "config" / "catalog_pipeline_policy.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def db_counts() -> dict[str, int]:
    db = SessionLocal()
    try:
        def c(*filters: Any) -> int:
            q = db.query(func.count(Product.id))
            for f in filters:
                q = q.filter(f)
            return int(q.scalar() or 0)

        return {
            "total_products": c(),
            "active_products": c(Product.status == "active"),
            "with_material_url": c(Product.material_url.isnot(None), Product.material_url != ""),
            "with_short_url": c(Product.short_url.isnot(None), Product.short_url != ""),
            "with_purchase_price": c(Product.purchase_price.isnot(None)),
            "with_basis_price": c(Product.basis_price.isnot(None)),
            "price_verified": c(Product.price_verified_at.isnot(None)),
            "exact_discount_true": c(Product.is_exact_discount == True),  # noqa: E712
            "merchant_recommendable_true": c(Product.merchant_recommendable == True),  # noqa: E712
            "allow_proactive_push_true": c(Product.allow_proactive_push == True),  # noqa: E712
        }
    finally:
        db.close()


def status_summary() -> dict[str, Any]:
    files = {
        "bulk_expand": ROOT / "run" / "bulk_catalog_expand_status.json",
        "catalog_refresh": ROOT / "run" / "catalog_refresh_status.json",
        "semi_pool": ROOT / "run" / "semi_recommend_pool_status.json",
        "commission_pool": ROOT / "run" / "commission_candidate_pool_status.json",
        "commission_short_link": ROOT / "run" / "commission_candidate_short_link_refresh_status.json",
        "free_llm_health_probe": ROOT / "run" / "free_llm_health_probe_status.json",
    }
    out: dict[str, Any] = {}
    for name, path in files.items():
        data = load_json(path, {})
        out[name] = {
            "status": data.get("status"),
            "updated_at": data.get("updated_at"),
            "finished_at": data.get("finished_at"),
            "candidate_count": data.get("candidate_count"),
            "tier_counts": data.get("tier_counts"),
            "attempted": data.get("attempted"),
            "updated": data.get("updated"),
            "failed": data.get("failed"),
            "last_error": data.get("last_error"),
        }
    return out


def build_plan(policy: dict[str, Any], counts: dict[str, int], statuses: dict[str, Any]) -> list[dict[str, Any]]:
    targets = policy.get("pool_targets", {})
    thresholds = policy.get("stage_thresholds", {})
    limits = policy.get("batch_limits", {})
    enabled = policy.get("enabled_jobs", {})

    commission_status = statuses.get("commission_pool", {})
    tier_counts = commission_status.get("tier_counts") or {}

    total_products = counts["total_products"]
    candidate_count = int(commission_status.get("candidate_count") or 0)
    main_ready = int(tier_counts.get("main_ready") or 0)
    semi_ready = int(tier_counts.get("semi_ready") or 0)
    semi_missing = int(tier_counts.get("semi_ready_missing_short_url") or 0)
    with_short_url = counts["with_short_url"]

    plan: list[dict[str, Any]] = []

    if enabled.get("bulk_expand_when_raw_below_target", True) and total_products < int(targets.get("raw_total_target", 0)):
        next_target = min(
            int(targets.get("raw_total_target", total_products)),
            total_products + int(limits.get("bulk_expand_target_increment", 100000)),
        )
        plan.append({
            "action": "bulk_expand_raw_pool",
            "reason": "raw_total_below_target",
            "current": total_products,
            "target": next_target,
            "jd_api": True
        })

    if enabled.get("build_commission_candidate_pool", True):
        plan.append({
            "action": "build_commission_candidate_pool",
            "reason": "refresh candidate tier counts after raw/short-link changes",
            "current_candidate_count": candidate_count,
            "jd_api": False
        })

    if (
        enabled.get("refresh_commission_candidate_short_links", True)
        and semi_missing >= int(thresholds.get("short_link_backfill_trigger_missing", 1000))
    ):
        plan.append({
            "action": "refresh_commission_candidate_short_links",
            "reason": "semi_ready_missing_short_url_above_trigger",
            "missing": semi_missing,
            "limit": int(limits.get("commission_short_link_limit_per_run", 3000)),
            "jd_api": True
        })

    if enabled.get("build_semi_recommend_pool", True):
        plan.append({
            "action": "build_semi_recommend_pool",
            "reason": "strict first-stage recommend pool refresh",
            "jd_api": False
        })

    if with_short_url < int(thresholds.get("min_short_url_coverage_for_commercial_smoke", 10000)):
        plan.append({
            "action": "commercial_readiness_hold",
            "reason": "short_url_coverage_below_commercial_smoke_threshold",
            "with_short_url": with_short_url,
            "threshold": int(thresholds.get("min_short_url_coverage_for_commercial_smoke", 10000)),
            "jd_api": False
        })

    plan.append({
        "action": "summary",
        "raw_total": total_products,
        "candidate_count": candidate_count,
        "main_ready": main_ready,
        "semi_ready": semi_ready,
        "semi_ready_missing_short_url": semi_missing,
        "with_short_url": with_short_url,
        "jd_api": False
    })
    return plan


def main() -> int:
    policy = load_json(DEFAULT_POLICY_PATH, {})
    counts = db_counts()
    statuses = status_summary()
    plan = build_plan(policy, counts, statuses)

    payload = {
        "job": "catalog_pipeline_planner",
        "status": "success",
        "policy_path": str(DEFAULT_POLICY_PATH),
        "counts": counts,
        "plan": plan
    }

    out = ROOT / "run" / "catalog_pipeline_plan.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    compact = {
        "status": "success",
        "raw_total": counts["total_products"],
        "with_short_url": counts["with_short_url"],
        "actions": [x["action"] for x in plan],
        "plan_path": str(out),
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
