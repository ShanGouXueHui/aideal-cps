import os
import re
import hashlib
import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from app.services.wechat_service import verify_wechat_signature, parse_wechat_xml
from app.services.message_router import route

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

TOKEN = os.getenv("WECHAT_TOKEN", "aideal_token")

_MENU_HANDLER_MAP = {
    "找商品": "find_product_entry",
    "今日推荐": "today_recommend",
    "合伙人中心": "partner_center_entry",
}


def _safe_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _openid_hash(openid: str) -> str:
    if not openid:
        return ""
    return hashlib.sha1(openid.encode("utf-8")).hexdigest()[:12]


def _preview_text(text: str, limit: int = 160) -> str:
    value = re.sub(r"\s+", " ", _safe_str(text))
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def _infer_handler(msg_type: str, event: str, event_key: str) -> str:
    if msg_type == "event" and event == "CLICK":
        return _MENU_HANDLER_MAP.get(event_key, f"event_click:{event_key or 'unknown'}")
    if msg_type == "event":
        return f"event:{event.lower() or 'unknown'}"
    if msg_type == "text":
        return "text_router"
    if msg_type:
        return f"{msg_type}_router"
    return "unknown_router"


@router.get("/wechat/callback")
async def verify(signature: str = "", timestamp: str = "", nonce: str = "", echostr: str = ""):
    if verify_wechat_signature(TOKEN, signature, timestamp, nonce):
        return PlainTextResponse(echostr)
    return "invalid"


@router.post("/wechat/callback")
async def callback(request: Request, signature: str = "", timestamp: str = "", nonce: str = ""):
    if not verify_wechat_signature(TOKEN, signature, timestamp, nonce):
        return Response("invalid", status_code=403)

    body = await request.body()
    msg = parse_wechat_xml(body)

    from_user = _safe_str(msg.get("FromUserName"))
    msg_type = _safe_str(msg.get("MsgType")).lower()
    event = _safe_str(msg.get("Event")).upper()
    event_key = _safe_str(msg.get("EventKey"))
    content = _safe_str(msg.get("Content"))
    matched_handler = _infer_handler(msg_type, event, event_key)

    logger.info(
        "wechat inbound | msg_type=%s event=%s event_key=%s openid_hash=%s matched_handler=%s content=%s",
        msg_type,
        event,
        event_key,
        _openid_hash(from_user),
        matched_handler,
        _preview_text(content),
    )

    resp = route(msg)

    logger.info(
        "wechat outbound | msg_type=%s event=%s event_key=%s openid_hash=%s matched_handler=%s reply_preview=%s",
        msg_type,
        event,
        event_key,
        _openid_hash(from_user),
        matched_handler,
        _preview_text(resp),
    )

    return Response(content=resp, media_type="application/xml")
