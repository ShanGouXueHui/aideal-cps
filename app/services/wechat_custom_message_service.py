from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
_TOKEN_CACHE: dict[str, float | str] = {"access_token": "", "expires_at": 0.0}


def _read_env_file() -> dict[str, str]:
    data: dict[str, str] = {}
    if not ENV_PATH.exists():
        return data
    try:
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        return data
    return data


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value not in (None, ""):
        return str(value).strip()
    return _read_env_file().get(name, default).strip()


def _wechat_api_request(method: str, url: str, **kwargs) -> dict:
    response = requests.request(method=method, url=url, timeout=15, **kwargs)
    response.raise_for_status()
    data = response.json()
    if data.get("errcode") not in (None, 0):
        raise RuntimeError(json.dumps(data, ensure_ascii=False))
    return data


def get_access_token(force_refresh: bool = False) -> str:
    now = time.time()
    cached_token = str(_TOKEN_CACHE.get("access_token") or "")
    cached_exp = float(_TOKEN_CACHE.get("expires_at") or 0)
    if cached_token and cached_exp - now > 120 and not force_refresh:
        return cached_token

    app_id = _env("WECHAT_MP_APP_ID")
    app_secret = _env("WECHAT_MP_APP_SECRET")
    if not app_id or not app_secret:
        raise RuntimeError("missing WECHAT_MP_APP_ID or WECHAT_MP_APP_SECRET")

    data = _wechat_api_request(
        "GET",
        "https://api.weixin.qq.com/cgi-bin/token",
        params={
            "grant_type": "client_credential",
            "appid": app_id,
            "secret": app_secret,
        },
    )
    access_token = str(data["access_token"])
    expires_in = int(data.get("expires_in") or 7200)
    _TOKEN_CACHE["access_token"] = access_token
    _TOKEN_CACHE["expires_at"] = now + expires_in
    return access_token


def send_custom_text(openid: str, content: str) -> None:
    access_token = get_access_token()
    _wechat_api_request(
        "POST",
        "https://api.weixin.qq.com/cgi-bin/message/custom/send",
        params={"access_token": access_token},
        json={
            "touser": openid,
            "msgtype": "text",
            "text": {"content": content},
        },
    )


def send_custom_news(openid: str, articles: list[dict]) -> None:
    payload_articles = []
    for article in (articles or [])[:8]:
        payload_articles.append(
            {
                "title": str(article.get("title") or "").strip(),
                "description": str(article.get("description") or "").strip(),
                "url": str(article.get("url") or "").strip(),
                "picurl": str(article.get("pic_url") or "").strip(),
            }
        )

    if not payload_articles:
        return

    access_token = get_access_token()
    _wechat_api_request(
        "POST",
        "https://api.weixin.qq.com/cgi-bin/message/custom/send",
        params={"access_token": access_token},
        json={
            "touser": openid,
            "msgtype": "news",
            "news": {"articles": payload_articles},
        },
    )


def send_custom_text_async(openid: str, content: str) -> None:
    threading.Thread(target=send_custom_text, args=(openid, content), daemon=True).start()


def send_custom_news_async(openid: str, articles: list[dict]) -> None:
    threading.Thread(target=send_custom_news, args=(openid, articles), daemon=True).start()
