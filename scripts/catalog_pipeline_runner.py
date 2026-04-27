#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "run" / "catalog_pipeline_plan.json"
JOBS_PATH = ROOT / "config" / "catalog_pipeline_jobs.json"
RUN_STATUS_PATH = ROOT / "run" / "catalog_pipeline_runner_status.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_status(payload: dict[str, Any]) -> None:
    RUN_STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_execution_plan(plan: dict[str, Any], registry: dict[str, Any]) -> list[dict[str, Any]]:
    runner_cfg = registry.get("runner", {})
    skip_actions = set(runner_cfg.get("skip_actions", []))
    allow_heavy = bool(runner_cfg.get("allow_heavy_jd_jobs", False))
    max_jobs = int(runner_cfg.get("max_executable_jobs_per_run", 3))
    jobs_cfg = registry.get("jobs", {})

    selected: list[dict[str, Any]] = []
    selected_count = 0

    for action_item in plan.get("plan", []):
        action = str(action_item.get("action") or "").strip()
        if not action or action in skip_actions:
            continue

        job = jobs_cfg.get(action)
        if not job or not job.get("enabled", False):
            continue

        risk_level = str(job.get("risk_level") or "")
        if risk_level == "jd_api_heavy" and not allow_heavy:
            selected.append({
                "action": action,
                "decision": "skipped",
                "reason": "heavy_jd_job_disabled_by_registry",
                "risk_level": risk_level,
            })
            continue

        if selected_count >= max_jobs:
            selected.append({
                "action": action,
                "decision": "skipped",
                "reason": "max_executable_jobs_per_run_reached",
                "risk_level": risk_level,
            })
            continue

        selected.append({
            "action": action,
            "decision": "selected",
            "risk_level": risk_level,
            "run_mode": job.get("run_mode"),
            "async_barrier": bool(job.get("async_barrier", False)),
            "command": job.get("command"),
        })
        selected_count += 1

    return selected


def run_selected(execution_plan: list[dict[str, Any]], *, dry_run: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    blocked_by_async: str | None = None

    for item in execution_plan:
        if item.get("decision") != "selected":
            results.append(item)
            continue

        if blocked_by_async:
            results.append({
                **item,
                "decision": "deferred",
                "status": "deferred_after_async_job",
                "reason": f"wait_for_{blocked_by_async}_to_finish",
            })
            continue

        command = str(item.get("command") or "").strip()
        if dry_run:
            results.append({**item, "status": "dry_run"})
            if item.get("async_barrier"):
                blocked_by_async = str(item.get("action") or "async_job")
            continue

        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )

        status = "success" if completed.returncode == 0 else "failed"
        result = {
            **item,
            "status": status,
            "returncode": completed.returncode,
            "output_tail": (completed.stdout or "")[-1200:],
        }
        results.append(result)

        if completed.returncode != 0:
            break

        if item.get("async_barrier"):
            blocked_by_async = str(item.get("action") or "async_job")

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    plan = load_json(PLAN_PATH, {})
    registry = load_json(JOBS_PATH, {})
    dry_run = not bool(args.execute)

    execution_plan = build_execution_plan(plan, registry)
    results = run_selected(execution_plan, dry_run=dry_run)

    failed = any(x.get("status") == "failed" for x in results)
    payload = {
        "job": "catalog_pipeline_runner",
        "status": "failed" if failed else "success",
        "dry_run": dry_run,
        "updated_at": now_iso(),
        "plan_path": str(PLAN_PATH),
        "jobs_path": str(JOBS_PATH),
        "results": results,
    }
    save_status(payload)

    compact = {
        "status": payload["status"],
        "dry_run": dry_run,
        "selected": [
            {
                "action": x.get("action"),
                "decision": x.get("decision"),
                "status": x.get("status"),
                "risk_level": x.get("risk_level"),
                "async_barrier": x.get("async_barrier"),
                "reason": x.get("reason"),
            }
            for x in results
        ],
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
