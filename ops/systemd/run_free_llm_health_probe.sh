#!/usr/bin/env bash
cd /home/deploy/projects/aideal-cps || exit 1

LOG_FILE="/home/deploy/projects/aideal-cps/logs/free_llm_health_probe.log"
STATUS_FILE="/home/deploy/projects/aideal-cps/run/free_llm_health_probe_status.json"
LOCK_FILE="/tmp/aideal_free_llm_health_probe.lock"
PY_BIN="/home/deploy/projects/aideal-cps/venv/bin/python"

mkdir -p /home/deploy/projects/aideal-cps/logs /home/deploy/projects/aideal-cps/run

START_TS="$(date '+%Y-%m-%d %H:%M:%S')"

{
  echo ""
  echo "===== FREE_LLM_HEALTH_PROBE START ${START_TS} ====="
} >> "$LOG_FILE"

if ! flock -n "$LOCK_FILE" bash -lc "
  cd /home/deploy/projects/aideal-cps &&
  PYTHONPATH=/home/deploy/projects/aideal-cps timeout 240 $PY_BIN scripts/refresh_free_llm_catalog.py >> \"$LOG_FILE\" 2>&1 || true
  PYTHONPATH=/home/deploy/projects/aideal-cps timeout 600 $PY_BIN scripts/probe_free_llm_health.py --mode background >> \"$LOG_FILE\" 2>&1
"; then
  END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
  cat > "$STATUS_FILE" <<JSON
{
  "job": "free_llm_health_probe",
  "status": "locked_or_failed",
  "started_at": "${START_TS}",
  "finished_at": "${END_TS}"
}
JSON
  {
    echo "===== FREE_LLM_HEALTH_PROBE END ${END_TS} status=locked_or_failed ====="
  } >> "$LOG_FILE"
  exit 1
fi

END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
cat > "$STATUS_FILE" <<JSON
{
  "job": "free_llm_health_probe",
  "status": "success",
  "started_at": "${START_TS}",
  "finished_at": "${END_TS}"
}
JSON

{
  echo "===== FREE_LLM_HEALTH_PROBE END ${END_TS} status=success ====="
} >> "$LOG_FILE"
