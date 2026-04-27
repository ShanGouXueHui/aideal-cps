#!/usr/bin/env bash
cd /home/deploy/projects/aideal-cps || exit 1

LOG_FILE="/home/deploy/projects/aideal-cps/logs/bulk_catalog_expand.log"
STATUS_FILE="/home/deploy/projects/aideal-cps/run/bulk_catalog_expand_status.json"
LOCK_FILE="/tmp/aideal_bulk_catalog_expand.lock"
PY_BIN="/home/deploy/projects/aideal-cps/venv/bin/python"

TARGET_TOTAL="${BULK_TARGET_TOTAL:-100000}"
WORKERS="${BULK_WORKERS:-10}"
KEYWORD_LIMIT="${BULK_KEYWORD_LIMIT:-0}"
PAGES_PER_KEYWORD="${BULK_PAGES_PER_KEYWORD:-45}"
ELITE_PAGES="${BULK_ELITE_PAGES:-20}"
PAGE_SIZE="${BULK_PAGE_SIZE:-50}"
MAX_REQUESTS="${BULK_MAX_REQUESTS:-14000}"
REQUEST_SLEEP="${BULK_REQUEST_SLEEP_SECONDS:-0.10}"

mkdir -p /home/deploy/projects/aideal-cps/logs /home/deploy/projects/aideal-cps/run

START_TS="$(date '+%Y-%m-%d %H:%M:%S')"

{
  echo ""
  echo "===== BULK_CATALOG_EXPAND START ${START_TS} ====="
  echo "TARGET_TOTAL=${TARGET_TOTAL} WORKERS=${WORKERS} KEYWORD_LIMIT=${KEYWORD_LIMIT} PAGES_PER_KEYWORD=${PAGES_PER_KEYWORD} PAGE_SIZE=${PAGE_SIZE} MAX_REQUESTS=${MAX_REQUESTS}"
} >> "$LOG_FILE"

if ! flock -n "$LOCK_FILE" bash -lc "cd /home/deploy/projects/aideal-cps && PYTHONPATH=/home/deploy/projects/aideal-cps $PY_BIN scripts/bulk_expand_jd_catalog.py --target-total \"$TARGET_TOTAL\" --workers \"$WORKERS\" --keyword-limit \"$KEYWORD_LIMIT\" --pages-per-keyword \"$PAGES_PER_KEYWORD\" --elite-pages \"$ELITE_PAGES\" --page-size \"$PAGE_SIZE\" --max-requests \"$MAX_REQUESTS\" --request-sleep-seconds \"$REQUEST_SLEEP\" --include-elite >> \"$LOG_FILE\" 2>&1"; then
  END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
  cat > "$STATUS_FILE" <<JSON
{
  "job": "bulk_catalog_expand",
  "status": "locked_or_failed",
  "started_at": "${START_TS}",
  "finished_at": "${END_TS}"
}
JSON
  {
    echo "===== BULK_CATALOG_EXPAND END ${END_TS} status=locked_or_failed ====="
  } >> "$LOG_FILE"
  exit 1
fi

END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
{
  echo "===== BULK_CATALOG_EXPAND END ${END_TS} status=finished ====="
} >> "$LOG_FILE"
