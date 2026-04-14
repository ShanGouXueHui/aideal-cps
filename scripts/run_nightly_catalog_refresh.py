from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.services.catalog_refresh_service import run_nightly_catalog_refresh


def main() -> int:
    db = SessionLocal()
    try:
        result = run_nightly_catalog_refresh(db)
        print(json.dumps(result, ensure_ascii=False, indent=2)[:12000])
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
