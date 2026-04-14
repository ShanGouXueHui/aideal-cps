from __future__ import annotations

from app.core.db import SessionLocal
from app.services.partner_center_action_service import route_partner_center_action
from app.services.partner_center_entry_service import get_partner_center_entry_reply
from app.services.partner_share_entry_service import get_partner_share_product_request_reply
from app.services.today_recommend_service import get_today_recommend_reply
from app.services.user_profile_service import (
    record_subscribe_event,
    update_user_profile_from_text,
)
from app.services.wechat_dialog_service import (
    get_help_reply,
    get_recommendation_reply,
    get_welcome_reply,
)
from app.services.wechat_menu_service import (
    get_menu_entry_reply,
    resolve_menu_entry_key,
)
from app.services.wechat_service import build_text_response


HELP_KEYWORDS = {"帮助", "怎么用", "如何使用", "使用说明", "help"}


def _build_reply(to_user: str, from_user: str, text: str) -> str:
    return build_text_response(to_user, from_user, text)


def route(msg: dict) -> str:
    to_user = msg.get("FromUserName")
    from_user = msg.get("ToUserName")
    msg_type = (msg.get("MsgType") or "").lower()

    if not to_user or not from_user:
        return ""

    if msg_type == "event":
        event = (msg.get("Event") or "").lower()

        if event == "subscribe":
            db = SessionLocal()
            try:
                record_subscribe_event(db, to_user)
            finally:
                db.close()
            return _build_reply(to_user, from_user, get_welcome_reply())

        if event == "click":
            event_key = (msg.get("EventKey") or "").strip()

            db = SessionLocal()
            try:
                partner_action_reply = route_partner_center_action(db, to_user, event_key)
                if partner_action_reply:
                    return _build_reply(to_user, from_user, partner_action_reply)

                menu_key = resolve_menu_entry_key(event_key)

                if menu_key == "today_recommend":
                    text = get_today_recommend_reply(db, to_user)
                    return _build_reply(to_user, from_user, text)

                if menu_key == "partner_center":
                    text = get_partner_center_entry_reply(db, to_user)
                    return _build_reply(to_user, from_user, text)
            finally:
                db.close()

            menu_reply = get_menu_entry_reply(event_key)
            if menu_reply:
                return _build_reply(to_user, from_user, menu_reply)
            return _build_reply(to_user, from_user, "已收到，你也可以直接告诉我想买什么。")

        return ""

    if msg_type == "text":
        content = (msg.get("Content") or "").strip()

        db = SessionLocal()
        try:
            share_product_reply = get_partner_share_product_request_reply(db, to_user, content)
            if share_product_reply:
                return _build_reply(to_user, from_user, share_product_reply)

            partner_action_reply = route_partner_center_action(db, to_user, content)
            if partner_action_reply:
                return _build_reply(to_user, from_user, partner_action_reply)

            menu_key = resolve_menu_entry_key(content)

            if menu_key == "today_recommend":
                text = get_today_recommend_reply(db, to_user)
                return _build_reply(to_user, from_user, text)

            if menu_key == "partner_center":
                text = get_partner_center_entry_reply(db, to_user)
                return _build_reply(to_user, from_user, text)

            menu_reply = get_menu_entry_reply(content)
            if menu_reply:
                return _build_reply(to_user, from_user, menu_reply)

            update_user_profile_from_text(db, to_user, content)

            if content in HELP_KEYWORDS:
                return _build_reply(to_user, from_user, get_help_reply())

            text = get_recommendation_reply(db, to_user, content)
            return _build_reply(to_user, from_user, text)
        finally:
            db.close()

    return _build_reply(to_user, from_user, "已收到")
