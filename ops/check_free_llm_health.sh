#!/usr/bin/env bash
cd /home/deploy/projects/aideal-cps || exit 1

echo "===== timer ====="
systemctl status aideal-free-llm-health-probe.timer --no-pager -l | sed -n '1,80p' || true

echo "===== service ====="
systemctl status aideal-free-llm-health-probe.service --no-pager -l | sed -n '1,100p' || true

echo "===== status file ====="
cat run/free_llm_health_probe_status.json 2>/dev/null || true

echo "===== active routing summary ====="
python - <<'PY'
import json
from pathlib import Path

p = Path("run/free_llm_active_routing.json")
if not p.exists():
    print("NO_ACTIVE_ROUTING")
    raise SystemExit(0)

data = json.loads(p.read_text(encoding="utf-8"))
print("mode =", data.get("mode"))
print("status =", data.get("status"))
print("generated_at =", data.get("generated_at"))
print("elapsed_ms =", data.get("elapsed_ms"))
print("probe_count =", data.get("probe_count"))
print("success_count =", data.get("success_count"))
print("provider_summary =", json.dumps(data.get("provider_summary") or {}, ensure_ascii=False, indent=2))

routes = data.get("routes") or {}
for task, rows in routes.items():
    print("task =", task, "route_count =", len(rows))
    for row in rows[:3]:
        print(" ", row)
PY

echo "===== recent log tail ====="
tail -n 120 logs/free_llm_health_probe.log 2>/dev/null || true
