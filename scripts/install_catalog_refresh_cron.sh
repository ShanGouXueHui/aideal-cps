#!/usr/bin/env bash

PROJECT_DIR="/home/deploy/projects/aideal-cps"
PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/catalog_refresh.log"

mkdir -p "$LOG_DIR"

tmpfile="$(mktemp)"
crontab -l 2>/dev/null | grep -v "run_nightly_catalog_refresh.py" > "$tmpfile"

echo "15 3 * * * flock -n /tmp/aideal_catalog_refresh.lock bash -lc 'cd $PROJECT_DIR && PYTHONPATH=$PROJECT_DIR $PYTHON_BIN $PROJECT_DIR/scripts/run_nightly_catalog_refresh.py >> $LOG_FILE 2>&1'" >> "$tmpfile"

crontab "$tmpfile"
rm -f "$tmpfile"

echo "===== installed cron ====="
crontab -l | grep "run_nightly_catalog_refresh.py"
