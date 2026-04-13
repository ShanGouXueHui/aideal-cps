from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.product import router as product_router


def build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(product_router)
    return app


def main() -> int:
    app = build_test_app()
    client = TestClient(app)

    print("=== GET /products?elite_id=129&has_short_url=true ===")
    r1 = client.get(
        "/products",
        params={
            "elite_id": 129,
            "has_short_url": "true",
            "page_size": 5,
            "order_by": "commission_rate",
            "sort": "desc",
        },
    )
    print(r1.status_code)
    print(json.dumps(r1.json(), ensure_ascii=False, indent=2)[:4000])

    if r1.status_code != 200:
        return 1

    data = r1.json()
    if data.get("total", 0) <= 0:
        print("FAIL: no products for elite_id=129")
        return 2

    print()
    print("=== GET /products?shop_name=合和泰 ===")
    r2 = client.get(
        "/products",
        params={
            "shop_name": "合和泰",
            "page_size": 5,
        },
    )
    print(r2.status_code)
    print(json.dumps(r2.json(), ensure_ascii=False, indent=2)[:4000])

    if r2.status_code != 200:
        return 3

    print("PASS: product pool smoke test ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
