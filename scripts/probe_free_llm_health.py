from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# FREE_LLM_SCRIPT_SYSPATH_GATE

from app.services.free_llm.health_probe_service import refresh_free_llm_health


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["quick", "background", "full"], default="quick")
    parser.add_argument("--max-models-per-provider", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument("--success-target", type=int, default=None)
    parser.add_argument("--total-timeout-seconds", type=int, default=None)
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args()

    result = refresh_free_llm_health(
        mode=args.mode,
        max_models_per_provider=args.max_models_per_provider,
        timeout_seconds=args.timeout_seconds,
        success_target=args.success_target,
        total_timeout_seconds=args.total_timeout_seconds,
    )

    print("FREE_LLM_HEALTH_PROBE_OK")
    print("mode =", result.get("mode"))
    print("status =", result.get("status"))
    print("elapsed_ms =", result.get("elapsed_ms"))
    print("stopped_reason =", result.get("stopped_reason"))
    print("probe_count =", result.get("probe_count"))
    print("success_count =", result.get("success_count"))

    print("provider_summary =")
    print(json.dumps(result.get("provider_summary") or {}, ensure_ascii=False, indent=2))

    routes = result.get("routes") or {}
    for task, rows in routes.items():
        print("task =", task, "route_count =", len(rows))
        for row in rows[:5]:
            print(" ", row)

    if args.print_json:
        p = Path("run/free_llm_health_snapshot.json")
        if p.exists():
            print(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
