from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.jd import router as jd_router


def build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(jd_router)
    return app


def main() -> int:
    app = build_test_app()
    client = TestClient(app)

    print("=== GET /jd/goods/top ===")
    r1 = client.get(
        "/jd/goods/top",
        params={"elite_id": 129, "limit": 3, "page_size": 5, "use_cache": False},
    )
    print(r1.status_code)
    print(json.dumps(r1.json(), ensure_ascii=False, indent=2)[:4000])

    if r1.status_code != 200:
        return 1

    rows = r1.json().get("rows", [])
    if not rows:
        print("FAIL: no rows in /jd/goods/top")
        return 2

    print()
    print("=== GET /jd/goods/top-with-links ===")
    r2 = client.get(
        "/jd/goods/top-with-links",
        params={"elite_id": 129, "limit": 2, "page_size": 5, "use_cache": False},
    )
    print(r2.status_code)
    print(json.dumps(r2.json(), ensure_ascii=False, indent=2)[:4000])

    if r2.status_code != 200:
        return 3

    rows2 = r2.json().get("rows", [])
    if not rows2:
        print("FAIL: no rows in /jd/goods/top-with-links")
        return 4

    first = rows2[0]
    material_id = first.get("materialUrl")
    short_url = first.get("shortURL")
    if not material_id or not short_url:
        print("FAIL: first row missing materialUrl or shortURL")
        return 5

    print()
    print("=== POST /jd/promotion/short-link ===")
    r3 = client.post("/jd/promotion/short-link", json={"material_id": material_id})
    print(r3.status_code)
    print(json.dumps(r3.json(), ensure_ascii=False, indent=2)[:4000])

    if r3.status_code != 200:
        return 6

    if not r3.json().get("shortURL"):
        print("FAIL: shortURL missing in /jd/promotion/short-link")
        return 7

    print("PASS: JD router smoke test ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
