import logging
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
from app.services.wechat_passive_fanout_service import fanout_text_messages_async
from app.services.wechat_recommend_runtime_service import (
    get_find_product_entry_text_reply,
    get_today_recommend_text_reply,
    get_today_recommend_text_segments,
    has_find_entry_product,
    has_today_recommend_products,
)
from app.services.wechat_service import build_text_response

logger = logging.getLogger("uvicorn.error")


HELP_KEYWORDS = {"帮助", "怎么用", "如何使用", "使用说明", "help"}
FIND_PRODUCT_KEYS = {"find_product", "find_product_entry", "找商品"}
TODAY_RECOMMEND_KEYS = {"today_recommend", "今日推荐"}
PARTNER_CENTER_KEYS = {"partner_center", "partner_center_entry", "合伙人中心"}


def _build_reply(to_user: str, from_user: str, text: str) -> str:
    return build_text_response(to_user, from_user, text)


def _normalize_menu_key(raw_key: str) -> str:
    raw_key = (raw_key or "").strip()
    resolved = resolve_menu_entry_key(raw_key)
    return (resolved or raw_key or "").strip()


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
            menu_key = _normalize_menu_key(event_key)

            db = SessionLocal()
            try:
                partner_action_reply = route_partner_center_action(db, to_user, event_key)
                if partner_action_reply:
                    return _build_reply(to_user, from_user, partner_action_reply)

                if menu_key in FIND_PRODUCT_KEYS:
                    if has_find_entry_product(db):
                        text = get_find_product_entry_text_reply(db, to_user)
                        if text:
                            return _build_reply(to_user, from_user, text)
                    return _build_reply(
                        to_user,
                        from_user,
                        "你可以直接回复想买的商品，比如：卫生纸、洗衣液、宝宝湿巾、京东自营。",
                    )

                if menu_key in TODAY_RECOMMEND_KEYS:
                    if has_today_recommend_products(db):
                        segments = get_today_recommend_text_segments(db, to_user)
                        if segments:
                            passive_reply = segments[0]
                            extra_replies = segments[1:]
                            if extra_replies:
                                try:
                                    logger.info("today_recommend extra_replies prepared | openid_hash=%s count=%s", (to_user or "")[-8:], len(extra_replies))

                                    fanout_text_messages_async(to_user, extra_replies)
                                except Exception:
                                    pass
                            return _build_reply(to_user, from_user, passive_reply)
                    text = get_today_recommend_reply(db, to_user)
                    return _build_reply(to_user, from_user, text)

                if menu_key in PARTNER_CENTER_KEYS:
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
        normalized_key = _normalize_menu_key(content)

        db = SessionLocal()
        try:
            share_product_reply = get_partner_share_product_request_reply(db, to_user, content)
            if share_product_reply:
                return _build_reply(to_user, from_user, share_product_reply)

            partner_action_reply = route_partner_center_action(db, to_user, content)
            if partner_action_reply:
                return _build_reply(to_user, from_user, partner_action_reply)

            if normalized_key in FIND_PRODUCT_KEYS:
                if has_find_entry_product(db):
                    text = get_find_product_entry_text_reply(db, to_user)
                    if text:
                        return _build_reply(to_user, from_user, text)
                return _build_reply(
                    to_user,
                    from_user,
                    "你可以直接回复想买的商品，比如：卫生纸、洗衣液、宝宝湿巾、京东自营。",
                )

            if normalized_key in TODAY_RECOMMEND_KEYS:
                if has_today_recommend_products(db):
                    text = get_today_recommend_text_reply(db, to_user)
                    if text:
                        return _build_reply(to_user, from_user, text)
                text = get_today_recommend_reply(db, to_user)
                return _build_reply(to_user, from_user, text)

            if normalized_key in PARTNER_CENTER_KEYS:
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
