from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.jd_union_workflow_service import JDUnionWorkflowService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elite-id", type=int, default=129)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--page-size", type=int, default=10)
    args = parser.parse_args()

    service = JDUnionWorkflowService()
    rows = service.query_goods_with_links(
        elite_id=args.elite_id,
        limit=args.limit,
        page_size=args.page_size,
    )

    print(json.dumps(rows, ensure_ascii=False, indent=2))
    if not rows:
        print("FAIL: no rows returned")
        return 1

    ok_count = sum(1 for row in rows if row.get("shortURL"))
    print(f"rows={len(rows)} ok_short_urls={ok_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
