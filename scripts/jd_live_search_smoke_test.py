from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.jd_live_search_service import search_live_jd_products


KEYWORDS = ["卫生纸", "卫生巾", "洗衣液"]


def main() -> int:
    for keyword in KEYWORDS:
        try:
            rows = search_live_jd_products(query_text=keyword, adult_verified=False, limit=5)
        except Exception as exc:
            print(json.dumps({
                "keyword": keyword,
                "error": str(exc),
            }, ensure_ascii=False, indent=2))
            continue

        print(json.dumps({
            "keyword": keyword,
            "rows": rows[:3],
        }, ensure_ascii=False, indent=2)[:6000])

        if rows:
            ok_links = sum(1 for row in rows if row.get("short_url") or row.get("product_url"))
            print(f"keyword={keyword} rows={len(rows)} ok_links={ok_links}")
            if ok_links == 0:
                print("FAIL: rows found but no usable links")
                return 3
            print("PASS: jd live search smoke test ok")
            return 0

    print("WARN: no rows found for all smoke keywords; external JD live search may need more coverage or permissions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
