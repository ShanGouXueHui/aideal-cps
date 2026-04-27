#!/usr/bin/env bash
cd /home/deploy/projects/aideal-cps || exit 1

REQUIRED_USER="${COMMISSION_SHORT_LINK_RUN_USER:-deploy}"
CURRENT_USER="$(id -un)"
if [ "$CURRENT_USER" != "$REQUIRED_USER" ]; then
  echo "ERROR: run_commission_candidate_short_link_refresh.sh must run as ${REQUIRED_USER}, current=${CURRENT_USER}. Use systemd-run --uid=${REQUIRED_USER} --gid=${REQUIRED_USER}."
  exit 1
fi

PY_BIN="/home/deploy/projects/aideal-cps/venv/bin/python"
LOG_FILE="/home/deploy/projects/aideal-cps/logs/commission_candidate_short_link_refresh_runner.log"
LOCK_FILE="/tmp/aideal_commission_candidate_short_link_refresh.lock"

LIMIT="${COMMISSION_SHORT_LINK_LIMIT:-}"

mkdir -p /home/deploy/projects/aideal-cps/logs /home/deploy/projects/aideal-cps/run

START_TS="$(date '+%Y-%m-%d %H:%M:%S')"
{
  echo ""
  echo "===== COMMISSION_CANDIDATE_SHORT_LINK_REFRESH START ${START_TS} ====="
  echo "LIMIT=${LIMIT:-config_default}"
} >> "$LOG_FILE"

if [ -n "$LIMIT" ]; then
  LIMIT_ARG="--limit \"$LIMIT\""
else
  LIMIT_ARG=""
fi

CMD="cd /home/deploy/projects/aideal-cps && PYTHONPATH=/home/deploy/projects/aideal-cps $PY_BIN scripts/build_commission_candidate_pool.py >> \"$LOG_FILE\" 2>&1 && PYTHONPATH=/home/deploy/projects/aideal-cps $PY_BIN scripts/refresh_commission_candidate_short_links.py $LIMIT_ARG >> \"$LOG_FILE\" 2>&1 && PYTHONPATH=/home/deploy/projects/aideal-cps $PY_BIN scripts/build_commission_candidate_pool.py >> \"$LOG_FILE\" 2>&1"

if ! flock -n "$LOCK_FILE" bash -lc "$CMD"; then
  END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
  {
    echo "===== COMMISSION_CANDIDATE_SHORT_LINK_REFRESH END ${END_TS} status=locked_or_failed ====="
  } >> "$LOG_FILE"
  exit 1
fi

END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
{
  echo "===== COMMISSION_CANDIDATE_SHORT_LINK_REFRESH END ${END_TS} status=finished ====="
} >> "$LOG_FILE"
