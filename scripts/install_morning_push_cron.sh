#!/usr/bin/env bash
PROJECT_DIR="/home/deploy/projects/aideal-cps"
VENV_PY="$PROJECT_DIR/venv/bin/python"
LOG_DIR="$PROJECT_DIR/data/logs"
mkdir -p "$LOG_DIR"

TMP_CRON="$(mktemp)"
crontab -l 2>/dev/null | grep -v "run_morning_push_job.py" > "$TMP_CRON" || true
echo "0 8 * * * cd $PROJECT_DIR && $VENV_PY scripts/run_morning_push_job.py --hour 8 --limit 50 --output-root data/morning_push_jobs >> $LOG_DIR/morning_push_job.log 2>&1" >> "$TMP_CRON"
crontab "$TMP_CRON"
rm -f "$TMP_CRON"
echo "installed morning push cron"
crontab -l | grep "run_morning_push_job.py"
