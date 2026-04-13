from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.message_router import route


CASES = [
    {
        "name": "subscribe",
        "msg": {
            "FromUserName": "test_user_openid",
            "ToUserName": "gh_aideal",
            "MsgType": "event",
            "Event": "subscribe",
        },
    },
    {
        "name": "shopping_query_1",
        "msg": {
            "FromUserName": "test_user_openid",
            "ToUserName": "gh_aideal",
            "MsgType": "text",
            "Content": "我想买一卷卫生纸",
        },
    },
    {
        "name": "shopping_query_2",
        "msg": {
            "FromUserName": "test_user_openid",
            "ToUserName": "gh_aideal",
            "MsgType": "text",
            "Content": "买一包夜用苏菲卫生巾，要求价格比京东官网便宜",
        },
    },
    {
        "name": "non_shopping",
        "msg": {
            "FromUserName": "test_user_openid",
            "ToUserName": "gh_aideal",
            "MsgType": "text",
            "Content": "你是谁",
        },
    },
]

for case in CASES:
    print(f"===== {case['name']} =====")
    print(route(case["msg"]))
    print()
