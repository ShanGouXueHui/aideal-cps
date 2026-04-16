from __future__ import annotations

import importlib
import logging
from typing import Any

from app.core.db import SessionLocal
from app.services.wechat_service import build_text_response

logger = logging.getLogger("uvicorn.error")


def _call_candidates(module_name: str, candidate_names: list[str], attempts: list[tuple[tuple[Any, ...], dict[str, Any]]]) -> Any:
    try:
        mod = importlib.import_module(module_name)
    except Exception:
        logger.exception("router import failed | module=%s", module_name)
        return None

    for name in candidate_names:
        fn = getattr(mod, name, None)
        if not callable(fn):
            continue

        for args, kwargs in attempts:
            try:
                result = fn(*args, **kwargs)
                if result is not None:
                    return result
            except TypeError:
                continue
            except Exception:
                logger.exception("router call failed | module=%s fn=%s", module_name, name)
                break
    return None


def _get_today_text(db, wechat_openid: str) -> str:
    result = _call_candidates(
        "app.services.wechat_recommend_runtime_service",
        ["get_today_recommend_text_reply"],
        [
            ((db, wechat_openid), {}),
            ((), {"db": db, "wechat_openid": wechat_openid}),
        ],
    )
    return str(result or "").strip()



def _get_find_entry_text(db, wechat_openid: str) -> str:
    result = _call_candidates(
        "app.services.wechat_recommend_runtime_service",
        ["get_find_product_entry_text_reply"],
        [
            ((db, wechat_openid), {}),
            ((), {"db": db, "wechat_openid": wechat_openid}),
        ],
    )
    return str(result or "").strip()


def _get_partner_center_text(db, wechat_openid: str) -> str:
    result = _call_candidates(
        "app.services.partner_center_entry_service",
        [
            "get_partner_center_entry_text_reply",
            "build_partner_center_entry_text_reply",
            "get_partner_center_entry_reply",
        ],
        [
            ((db, wechat_openid), {}),
            ((), {"db": db, "wechat_openid": wechat_openid}),
        ],
    )
    return str(result or "").strip()


def _get_dialog_text(db, wechat_openid: str, content: str, msg_type: str) -> str:
    result = _call_candidates(
        "app.services.wechat_dialog_service",
        [
            "get_text_reply",
            "get_dialog_text_reply",
            "get_wechat_text_reply",
            "reply_for_user_message",
            "handle_text_message",
            "handle_user_message",
        ],
        [
            ((), {"db": db, "wechat_openid": wechat_openid, "content": content, "msg_type": msg_type}),
            ((db, wechat_openid, content), {}),
            ((db, content, wechat_openid), {}),
            ((wechat_openid, content), {}),
            ((), {"db": db, "openid": wechat_openid, "content": content}),
            ((), {"db": db, "user_id": wechat_openid, "content": content}),
        ],
    )
    return str(result or "").strip()


def route(
    to_user: str,
    from_user: str,
    msg_type: str,
    content: str = "",
    event: str = "",
    event_key: str = "",
    **kwargs,
) -> str:
    if msg_type == "event" and event == "CLICK" and event_key == "今日推荐":
        db = SessionLocal()
        try:
            text = _get_today_text(db, to_user)
        finally:
            db.close()

        if not text:
            text = "今天的推荐还在准备中，稍后再试一下～"

        logger.info(
            "today_recommend passive-only branch | openid_tail=%s text_len=%s",
            (to_user or "")[-8:],
            len(text),
        )
        return build_text_response(to_user, from_user, text)

    if msg_type == "event" and event == "CLICK" and event_key == "找商品":
        db = SessionLocal()
        try:
            text = _get_find_entry_text(db, to_user)
        finally:
            db.close()

        if not text:
            text = "可以直接回复你想买的商品，比如：洗衣液、卫生纸、宝宝湿巾。"
        return build_text_response(to_user, from_user, text)

    if msg_type == "event" and event == "CLICK" and event_key == "合伙人中心":
        db = SessionLocal()
        try:
            text = _get_partner_center_text(db, to_user)
        finally:
            db.close()

        if not text:
            text = "合伙人中心正在准备中，稍后再试一下～"
        return build_text_response(to_user, from_user, text)

    if msg_type == "text":
        db = SessionLocal()
        try:
            text = _get_dialog_text(db, to_user, content, msg_type)
        finally:
            db.close()

        if not text:
            text = "可以直接回复你想买的商品，比如：洗衣液、卫生纸、宝宝湿巾。"
        return build_text_response(to_user, from_user, text)

    return build_text_response(
        to_user,
        from_user,
        "可以直接回复你想买的商品，比如：洗衣液、卫生纸、宝宝湿巾。",
    )
