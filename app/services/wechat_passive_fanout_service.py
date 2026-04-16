from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Iterable

import requests

from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
CUSTOM_SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/custom/send"

_ACCESS_TOKEN: str | None = None
_ACCESS_TOKEN_EXPIRES_AT: float = 0.0
_LOCK = threading.Lock()


def _openid_hash(openid: str) -> str:
    if not openid:
        return "empty"
    return hashlib.sha1(openid.encode("utf-8")).hexdigest()[:12]


def _get_access_token() -> str:
    global _ACCESS_TOKEN, _ACCESS_TOKEN_EXPIRES_AT

    now = time.time()
    if _ACCESS_TOKEN and now < _ACCESS_TOKEN_EXPIRES_AT - 60:
        return _ACCESS_TOKEN

    with _LOCK:
        now = time.time()
        if _ACCESS_TOKEN and now < _ACCESS_TOKEN_EXPIRES_AT - 60:
            return _ACCESS_TOKEN

        resp = requests.get(
            TOKEN_URL,
            params={
                "grant_type": "client_credential",
                "appid": settings.WECHAT_MP_APP_ID,
                "secret": settings.WECHAT_MP_APP_SECRET,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 7200) or 7200)
        errcode = int(data.get("errcode", 0) or 0)

        if errcode != 0 or not token:
            raise RuntimeError(f"get_access_token_failed: {data}")

        _ACCESS_TOKEN = token
        _ACCESS_TOKEN_EXPIRES_AT = time.time() + expires_in
        return token


def _send_text(openid: str, text: str) -> None:
    token = _get_access_token()
    resp = requests.post(
        f"{CUSTOM_SEND_URL}?access_token={token}",
        json={
            "touser": openid,
            "msgtype": "text",
            "text": {"content": text},
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    errcode = int(data.get("errcode", 0) or 0)
    if errcode != 0:
        raise RuntimeError(f"custom_send_failed: {data}")


def _worker(openid: str, texts: list[str]) -> None:
    openid_hash = _openid_hash(openid)
    logger.info(
        "wechat custom fanout queued | openid_hash=%s count=%s",
        openid_hash,
        len(texts),
    )
    for idx, text in enumerate(texts, start=1):
        try:
            _send_text(openid, text)
            logger.info(
                "wechat custom fanout sent | openid_hash=%s index=%s len=%s",
                openid_hash,
                idx,
                len(text),
            )
        except Exception as exc:
            logger.exception(
                "wechat custom fanout failed | openid_hash=%s index=%s error=%s",
                openid_hash,
                idx,
                exc,
            )
        time.sleep(0.8)


def fanout_text_messages_async(openid: str, texts: Iterable[str]) -> None:
    clean_texts = [str(x).strip() for x in texts if str(x or "").strip()]
    if not openid or not clean_texts:
        logger.info(
            "wechat custom fanout skipped | openid_hash=%s count=%s",
            _openid_hash(openid),
            len(clean_texts),
        )
        return

    thread = threading.Thread(
        target=_worker,
        args=(openid, clean_texts),
        name=f"wechat-fanout-{_openid_hash(openid)}",
        daemon=True,
    )
    thread.start()
