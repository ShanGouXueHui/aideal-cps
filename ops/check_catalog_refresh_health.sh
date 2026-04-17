#!/usr/bin/env bash
cd /home/deploy/projects/aideal-cps || exit 1

echo "===== timer ====="
systemctl status aideal-catalog-refresh.timer --no-pager -l | sed -n '1,80p'

echo "===== service ====="
systemctl status aideal-catalog-refresh.service --no-pager -l | sed -n '1,120p'

echo "===== status file ====="
cat run/catalog_refresh_status.json 2>/dev/null || echo "missing: run/catalog_refresh_status.json"

echo "===== recent journal ====="
journalctl -u aideal-catalog-refresh.service -n 50 --no-pager

echo "===== recent log tail ====="
tail -n 120 logs/catalog_refresh.log 2>/dev/null || true

echo "===== active sku type summary ====="
python - <<'PY'
from sqlalchemy import text
from app.core.db import SessionLocal

db = SessionLocal()
try:
    rows = db.execute(text("""
        SELECT
          CASE WHEN jd_sku_id REGEXP '^[0-9]+$' THEN 'numeric' ELSE 'non_numeric' END AS sku_type,
          COUNT(*) AS cnt
        FROM products
        WHERE status = 'active'
        GROUP BY sku_type
        ORDER BY sku_type
    """)).fetchall()
    for row in rows:
        print(row)
finally:
    db.close()
PY
