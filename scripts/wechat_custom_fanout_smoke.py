from __future__ import annotations

import argparse
from dotenv import load_dotenv

load_dotenv(".env", override=True)

from app.services.wechat_passive_fanout_service import fanout_text_messages

parser = argparse.ArgumentParser()
parser.add_argument("--openid", required=True)
parser.add_argument("--text", action="append", required=True)
args = parser.parse_args()

res = fanout_text_messages(args.openid, args.text)
print(res)
