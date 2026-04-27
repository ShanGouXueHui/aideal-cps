#!/usr/bin/env bash
cd /home/deploy/projects/aideal-cps || exit 1


REQUIRED_USER="${SEMI_RUN_USER:-deploy}"
CURRENT_USER="$(id -un)"
if [ "$CURRENT_USER" != "$REQUIRED_USER" ]; then
  echo "ERROR: run_semi_pool_refresh.sh must run as ${REQUIRED_USER}, current=${CURRENT_USER}. Use systemd-run --uid=${REQUIRED_USER} --gid=${REQUIRED_USER}."
  exit 1
fi

PY_BIN="/home/deploy/projects/aideal-cps/venv/bin/python"
LOG_FILE="/home/deploy/projects/aideal-cps/logs/semi_pool_refresh.log"
LOCK_FILE="/tmp/aideal_semi_pool_refresh.lock"

CANDIDATE_LIMIT="${SEMI_CANDIDATE_LIMIT:-5000}"
MAX_PER_CATEGORY="${SEMI_MAX_PER_CATEGORY:-160}"
SHORT_LINK_LIMIT="${SEMI_SHORT_LINK_LIMIT:-300}"
REQUEST_SLEEP="${SEMI_REQUEST_SLEEP_SECONDS:-0.25}"

mkdir -p /home/deploy/projects/aideal-cps/logs /home/deploy/projects/aideal-cps/run

START_TS="$(date '+%Y-%m-%d %H:%M:%S')"
{
  echo ""
  echo "===== SEMI_POOL_REFRESH START ${START_TS} ====="
  echo "CANDIDATE_LIMIT=${CANDIDATE_LIMIT} MAX_PER_CATEGORY=${MAX_PER_CATEGORY} SHORT_LINK_LIMIT=${SHORT_LINK_LIMIT} REQUEST_SLEEP=${REQUEST_SLEEP}"
} >> "$LOG_FILE"

if ! flock -n "$LOCK_FILE" bash -lc "cd /home/deploy/projects/aideal-cps && PYTHONPATH=/home/deploy/projects/aideal-cps $PY_BIN scripts/build_semi_recommend_pool.py --candidate-limit \"$CANDIDATE_LIMIT\" --max-per-category \"$MAX_PER_CATEGORY\" >> \"$LOG_FILE\" 2>&1 && PYTHONPATH=/home/deploy/projects/aideal-cps $PY_BIN scripts/refresh_semi_candidate_short_links.py --limit \"$SHORT_LINK_LIMIT\" --request-sleep-seconds \"$REQUEST_SLEEP\" >> \"$LOG_FILE\" 2>&1"; then
  END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
  {
    echo "===== SEMI_POOL_REFRESH END ${END_TS} status=locked_or_failed ====="
  } >> "$LOG_FILE"
  exit 1
fi

END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
{
  echo "===== SEMI_POOL_REFRESH END ${END_TS} status=finished ====="
} >> "$LOG_FILE"
