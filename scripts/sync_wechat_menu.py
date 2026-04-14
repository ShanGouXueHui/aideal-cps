from __future__ import annotations

import json

from app.services.wechat_menu_sync_service import sync_wechat_menu


def main() -> int:
    result = sync_wechat_menu()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    create_result = result.get("create_result") or {}
    if create_result.get("errcode") not in (0, None):
        print("FAIL: wechat menu create failed")
        return 1
    print("PASS: wechat menu sync ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
