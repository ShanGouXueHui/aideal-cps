#!/usr/bin/env bash
cd /home/deploy/projects/aideal-cps || exit 1

LOG_FILE="/home/deploy/projects/aideal-cps/logs/catalog_refresh.log"
STATUS_FILE="/home/deploy/projects/aideal-cps/run/catalog_refresh_status.json"
LOCK_FILE="/tmp/aideal_catalog_refresh.lock"
PY_BIN="/home/deploy/projects/aideal-cps/venv/bin/python"

mkdir -p /home/deploy/projects/aideal-cps/logs /home/deploy/projects/aideal-cps/run

START_TS="$(date '+%Y-%m-%d %H:%M:%S')"

{
  echo ""
  echo "===== SYSTEMD_CATALOG_REFRESH START ${START_TS} ====="
} >> "$LOG_FILE"

if ! flock -n "$LOCK_FILE" bash -lc "cd /home/deploy/projects/aideal-cps && PYTHONPATH=/home/deploy/projects/aideal-cps $PY_BIN scripts/run_nightly_catalog_refresh.py >> \"$LOG_FILE\" 2>&1"; then
  END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
  cat > "$STATUS_FILE" <<JSON
{
  "job": "catalog_refresh",
  "status": "locked_or_failed",
  "started_at": "${START_TS}",
  "finished_at": "${END_TS}"
}
JSON
  {
    echo "===== SYSTEMD_CATALOG_REFRESH END ${END_TS} status=locked_or_failed ====="
  } >> "$LOG_FILE"
  exit 1
fi

END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
cat > "$STATUS_FILE" <<JSON
{
  "job": "catalog_refresh",
  "status": "success",
  "started_at": "${START_TS}",
  "finished_at": "${END_TS}"
}
JSON

{
  echo "===== SYSTEMD_CATALOG_REFRESH END ${END_TS} status=success ====="
} >> "$LOG_FILE"
