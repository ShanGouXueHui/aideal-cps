from app.core.db import SessionLocal
from app.services.user_service import get_or_create_user_by_openid
from app.services.wechat_dialog_service import (
    get_help_reply,
    get_recommendation_reply,
    get_welcome_reply,
)
from app.services.wechat_service import build_text_response


HELP_KEYWORDS = {"帮助", "怎么用", "如何使用", "使用说明", "help"}


def route(msg):
    to_user = msg.get("FromUserName")
    from_user = msg.get("ToUserName")
    msg_type = (msg.get("MsgType") or "").lower()

    if to_user:
        get_or_create_user_by_openid(to_user)

    if msg_type == "event":
        event = (msg.get("Event") or "").lower()
        if event == "subscribe":
            return build_text_response(to_user, from_user, get_welcome_reply())
        return ""

    if msg_type == "text":
        content = (msg.get("Content") or "").strip()
        if content in HELP_KEYWORDS:
            return build_text_response(to_user, from_user, get_help_reply())

        db = SessionLocal()
        try:
            text = get_recommendation_reply(db, to_user, content)
            return build_text_response(to_user, from_user, text)
        finally:
            db.close()

    return build_text_response(to_user, from_user, "已收到")
