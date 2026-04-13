from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.jd_union_client import (
    JDUnionClient,
    extract_jingfen_items,
    extract_promotion_payload,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elite-id", type=int, default=129)
    parser.add_argument("--page-size", type=int, default=3)
    parser.add_argument("--with-promotion", action="store_true")
    args = parser.parse_args()

    client = JDUnionClient()

    print("=== jingfen.query ===")
    goods_response = client.jingfen_query(elite_id=args.elite_id, page_size=args.page_size)
    print(json.dumps(goods_response, ensure_ascii=False, indent=2)[:4000])

    items = extract_jingfen_items(goods_response)
    print(f"items_count={len(items)}")

    if not items:
        print("FAIL: no items extracted from jingfen response")
        return 1

    first_item = items[0]
    material_id = first_item.get("materialUrl")
    print(f"first_material_id={material_id}")

    if not args.with_promotion:
        print("PASS: jingfen.query ok")
        return 0

    if not material_id:
        print("FAIL: first item has no materialUrl, cannot test promotion")
        return 2

    print()
    print("=== promotion.bysubunionid.get ===")
    promotion_response = client.promotion_bysubunionid_get(material_id=material_id)
    print(json.dumps(promotion_response, ensure_ascii=False, indent=2)[:4000])

    promotion_payload = extract_promotion_payload(promotion_response)
    if isinstance(promotion_payload, dict):
        print(f"promotion_payload_keys={list(promotion_payload.keys())}")
    else:
        print(f"promotion_payload_type={type(promotion_payload).__name__}")

    if isinstance(promotion_payload, dict) and (
        "clickURL" in promotion_payload
        or "shortURL" in promotion_payload
        or "data" in promotion_payload
    ):
        print("PASS: promotion.bysubunionid.get looks successful")
        return 0

    print("WARN: promotion response did not expose clickURL/shortURL directly, inspect raw JSON above")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
