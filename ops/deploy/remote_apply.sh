#!/usr/bin/env bash
cd "$(dirname "$0")/../.." || exit 1

TARGETS_FILE="${TARGETS_FILE:-ops/deploy/targets.env}"
if [ ! -f "$TARGETS_FILE" ]; then
  echo "missing targets file: $TARGETS_FILE"
  exit 1
fi

. "$TARGETS_FILE"

SSH_TARGET="${TARGET_SSH_HOST:-$TARGET_HOST}"

ssh "$SSH_TARGET" "PROJECT_PATH='$TARGET_PATH' SERVICE_NAME='$TARGET_SERVICE' bash -s" <<'REMOTE'
echo "===== REMOTE BASIC ====="
whoami
hostname
cd "$PROJECT_PATH" || exit 1
pwd

echo
echo "===== REMOTE PYTHON / PIP ====="
./venv/bin/python --version
./venv/bin/pip install -r requirements.txt

echo
echo "===== REMOTE COMPILE ====="
./venv/bin/python -m compileall app scripts main.py

echo
echo "===== REMOTE IMPORT CHECK ====="
./venv/bin/python - <<'PY'
import importlib
mods = [
    "main",
    "app.main",
    "app.api.wechat",
    "app.api.wechat_recommend_h5",
    "app.api.promotion",
    "app.api.jd",
    "app.api.partner",
    "app.services.message_router",
    "app.services.wechat_recommend_runtime_service",
]
for name in mods:
    importlib.import_module(name)
    print("ok:", name)
print("remote_import_all_ok = true")
PY

echo
echo "===== REMOTE ROUTE CHECK ====="
./venv/bin/python - <<'PY'
from app.main import app
wanted = {
    "/wechat/callback",
    "/api/h5/recommend/{product_id}",
    "/api/h5/recommend/more-like-this",
    "/api/promotion/redirect",
    "/promotion/redirect",
    "/jd/goods/top",
    "/jd/goods/top-with-links",
    "/jd/promotion/short-link",
}
rows = []
for r in app.routes:
    path = getattr(r, "path", "")
    methods = sorted(list(getattr(r, "methods", []) or []))
    if path in wanted:
        rows.append({"path": path, "methods": methods, "name": getattr(r, "name", "")})
for row in sorted(rows, key=lambda x: x["path"]):
    print(row)
print("remote_route_count =", len(rows))
PY

echo
echo "===== REMOTE PROBE PRODUCT ====="
PROBE_PRODUCT_ID=$(
./venv/bin/python - <<'PY'
from app.core.db import SessionLocal
from app.models.product import Product

db = SessionLocal()
try:
    p = (
        db.query(Product)
        .filter(
            Product.is_active == True,
            Product.short_url.isnot(None),
            Product.short_url != "",
        )
        .order_by(Product.id.asc())
        .first()
    )
    print(p.id if p else "")
finally:
    db.close()
PY
)
echo "probe_product_id=${PROBE_PRODUCT_ID}"

echo
echo "===== REMOTE RECOMMEND RUNTIME SMOKE ====="
./venv/bin/python - <<'PY'
from app.core.db import SessionLocal
from app.services.wechat_recommend_runtime_service import (
    has_today_recommend_products,
    has_find_entry_product,
    get_today_recommend_text_reply,
    get_find_product_entry_text_reply,
)

db = SessionLocal()
try:
    t = get_today_recommend_text_reply(db, "deploy_probe_runtime")
    f = get_find_product_entry_text_reply(db, "deploy_probe_runtime")
    print("has_today_recommend_products =", has_today_recommend_products(db))
    print("has_find_entry_product =", has_find_entry_product(db))
    print("today_text_len =", len(t or ""))
    print("find_text_len =", len(f or ""))
    print("today_has_detail =", "图文详情" in (t or ""))
    print("today_has_buy =", "下单链接" in (t or ""))
    print("today_has_more =", "更多同类产品" in (t or ""))
    print("find_has_detail =", "图文详情" in (f or ""))
    print("find_has_buy =", "下单链接" in (f or ""))
    print("find_has_more =", "更多同类产品" in (f or ""))
finally:
    db.close()
PY

echo
echo "===== REMOTE RESTART ====="
RESTART_DONE=0
if sudo -n systemctl restart "$SERVICE_NAME" >/dev/null 2>&1; then
  RESTART_DONE=1
  echo "restart_mode=sudo_nopasswd"
else
  echo "restart_requires_manual_sudo=true"
fi

if [ "$RESTART_DONE" = "1" ]; then
  sleep 2

  echo
  echo "===== REMOTE SERVICE STATUS ====="
  systemctl status "$SERVICE_NAME" --no-pager | sed -n '1,12p'

  echo
  echo "===== REMOTE CALLBACK PROBE ====="
  curl -sS -i 'http://127.0.0.1:8000/wechat/callback?signature=test&timestamp=1&nonce=1&echostr=ok' | sed -n '1,8p'

  if [ -n "$PROBE_PRODUCT_ID" ]; then
    echo
    echo "===== REMOTE DETAIL PROBE ====="
    curl -sS -o /dev/null -D - "http://127.0.0.1:8000/api/h5/recommend/${PROBE_PRODUCT_ID}?scene=today_recommend&slot=1" | sed -n '1,8p'

    echo
    echo "===== REMOTE MORE-LIKE-THIS PROBE ====="
    curl -sS -o /dev/null -D - "http://127.0.0.1:8000/api/h5/recommend/more-like-this?product_id=${PROBE_PRODUCT_ID}&scene=today_recommend&slot=1&wechat_openid=deploy_probe_runtime" | sed -n '1,8p'

    echo
    echo "===== REMOTE REDIRECT PROBE ====="
    curl -sS -o /dev/null -D - "http://127.0.0.1:8000/api/promotion/redirect?wechat_openid=deploy_probe_runtime&product_id=${PROBE_PRODUCT_ID}&scene=today_recommend&slot=1" | sed -n '1,8p'
  fi
fi
REMOTE
