from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import SessionLocal
from app.services.morning_push_job_service import build_morning_push_job


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hour", type=int, default=8)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--mark-sent", action="store_true")
    parser.add_argument("--output-root", default="data/morning_push_jobs")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = build_morning_push_job(
            db,
            current_hour=args.hour,
            limit=args.limit,
            output_root=args.output_root,
            mark_sent=args.mark_sent,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
