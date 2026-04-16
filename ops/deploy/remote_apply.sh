#!/usr/bin/env bash

PROJECT_PATH="${1:-/home/deploy/projects/aideal-cps}"
SERVICE_NAME="${2:-aideal.service}"

cd "$PROJECT_PATH" || exit 1

echo "===== REMOTE PROJECT ====="
pwd
git branch --show-current || true
git status --short || true

echo
echo "===== PYTHON ====="
python3 -V || true

if [ -f venv/bin/python ]; then
  echo
  echo "===== COMPILE ====="
  PYTHONPATH="$PROJECT_PATH" venv/bin/python -m compileall app main.py scripts || true
fi

echo
echo "===== SERVICE STATUS BEFORE ====="
sudo systemctl status "$SERVICE_NAME" --no-pager || true

echo
echo "===== RESTART ====="
sudo systemctl restart "$SERVICE_NAME"
sleep 2
sudo systemctl status "$SERVICE_NAME" --no-pager || true

echo
echo "===== LOCAL PROBES ====="
curl -i "http://127.0.0.1:8000/wechat/callback?signature=test&timestamp=1&nonce=1&echostr=ok" || true
