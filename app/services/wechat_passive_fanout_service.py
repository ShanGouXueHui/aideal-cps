from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

TOKEN_CACHE_PATH = Path("data/wechat_runtime/access_token.json")
TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
CUSTOM_SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/custom/send"


def _read_cache() -> dict | None:
    if not TOKEN_CACHE_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cache(access_token: str, expires_in: int) -> None:
    TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "access_token": access_token,
        "expires_at": int(time.time()) + max(int(expires_in) - 300, 300),
    }
    TOKEN_CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _fetch_access_token() -> str:
    app_id = (getattr(settings, "WECHAT_MP_APP_ID", "") or "").strip()
    app_secret = (getattr(settings, "WECHAT_MP_APP_SECRET", "") or "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("WECHAT_MP_APP_ID / WECHAT_MP_APP_SECRET missing")

    resp = requests.get(
        TOKEN_URL,
        params={
            "grant_type": "client_credential",
            "appid": app_id,
            "secret": app_secret,
        },
        timeout=8,
    )
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"fetch access_token failed: {data}")
    _write_cache(token, int(data.get("expires_in") or 7200))
    return token


def get_access_token() -> str:
    cache = _read_cache()
    if cache:
        token = str(cache.get("access_token") or "").strip()
        expires_at = int(cache.get("expires_at") or 0)
        if token and expires_at > int(time.time()):
            return token
    return _fetch_access_token()


def fanout_text_messages(wechat_openid: str, texts: list[str]) -> list[dict]:
    wechat_openid = (wechat_openid or "").strip()
    payload_texts = [str(x or "").strip() for x in texts if str(x or "").strip()]
    if not wechat_openid or not payload_texts:
        return []

    token = get_access_token()
    results: list[dict] = []

    for idx, text in enumerate(payload_texts, start=1):
        resp = requests.post(
            f"{CUSTOM_SEND_URL}?access_token={token}",
            json={
                "touser": wechat_openid,
                "msgtype": "text",
                "text": {"content": text},
            },
            timeout=8,
        )
        try:
            data = resp.json()
        except Exception:
            data = {
                "http_status": resp.status_code,
                "text": resp.text[:500],
            }
        results.append(data)
        logger.info(
            "wechat custom fanout | openid_hash=%s idx=%s errcode=%s errmsg=%s",
            wechat_openid[-8:] if wechat_openid else "",
            idx,
            data.get("errcode"),
            data.get("errmsg"),
        )

    return results


def fanout_text_messages_async(wechat_openid: str, texts: list[str]) -> None:
    def _worker():
        try:
            fanout_text_messages(wechat_openid, texts)
        except Exception as exc:
            logger.exception("wechat custom fanout failed | exc=%s", exc)

    threading.Thread(
        target=_worker,
        name="wechat-custom-fanout",
        daemon=True,
    ).start()
