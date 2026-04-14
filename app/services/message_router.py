from app.core.db import SessionLocal
from app.services.user_profile_service import record_subscribe_event, update_user_profile_from_text
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

    if msg_type == "event":
        event = (msg.get("Event") or "").lower()
        if event == "subscribe" and to_user:
            db = SessionLocal()
            try:
                record_subscribe_event(db, to_user)
            finally:
                db.close()
            return build_text_response(to_user, from_user, get_welcome_reply())
        return ""

    if msg_type == "text" and to_user:
        content = (msg.get("Content") or "").strip()
        db = SessionLocal()
        try:
            update_user_profile_from_text(db, to_user, content)

            if content in HELP_KEYWORDS:
                return build_text_response(to_user, from_user, get_help_reply())

            text = get_recommendation_reply(db, to_user, content)
            return build_text_response(to_user, from_user, text)
        finally:
            db.close()

    return build_text_response(to_user, from_user, "已收到")
