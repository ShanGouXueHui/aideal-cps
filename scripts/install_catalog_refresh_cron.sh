#!/usr/bin/env bash

PROJECT_DIR="/home/deploy/projects/aideal-cps"
PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
RUN_SCRIPT="$PROJECT_DIR/scripts/run_nightly_catalog_refresh.py"
LOG_FILE="$PROJECT_DIR/logs/catalog_refresh.log"
LOCK_FILE="/tmp/aideal_catalog_refresh.lock"
CRON_EXPR="15 3 * * *"

mkdir -p "$PROJECT_DIR/logs"

CRON_LINE="$CRON_EXPR flock -n $LOCK_FILE bash -lc 'cd $PROJECT_DIR && $PYTHON_BIN $RUN_SCRIPT >> $LOG_FILE 2>&1'"

TMP_CRON="$(mktemp)"
crontab -l 2>/dev/null | grep -v 'run_nightly_catalog_refresh.py' > "$TMP_CRON" || true
echo "$CRON_LINE" >> "$TMP_CRON"
crontab "$TMP_CRON"
rm -f "$TMP_CRON"

echo "===== installed cron ====="
crontab -l | grep 'run_nightly_catalog_refresh.py' || true
