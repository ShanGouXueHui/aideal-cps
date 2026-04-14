from __future__ import annotations

import json
import os
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MENU_CONFIG_PATH = PROJECT_ROOT / "config" / "wechat_mp_menu.json"


def load_wechat_menu_payload() -> dict:
    return json.loads(MENU_CONFIG_PATH.read_text(encoding="utf-8"))


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"missing env: {name}")
    return value


def get_wechat_access_token() -> str:
    app_id = _require_env("WECHAT_MP_APP_ID")
    app_secret = _require_env("WECHAT_MP_APP_SECRET")

    url = "https://api.weixin.qq.com/cgi-bin/token"
    params = {
        "grant_type": "client_credential",
        "appid": app_id,
        "secret": app_secret,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"get access token failed: {data}")
    return token


def create_wechat_menu(access_token: str, payload: dict) -> dict:
    url = f"https://api.weixin.qq.com/cgi-bin/menu/create?access_token={access_token}"
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_wechat_menu(access_token: str) -> dict:
    url = f"https://api.weixin.qq.com/cgi-bin/get_current_selfmenu_info?access_token={access_token}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def sync_wechat_menu() -> dict:
    payload = load_wechat_menu_payload()
    token = get_wechat_access_token()
    create_result = create_wechat_menu(token, payload)
    current_menu = get_wechat_menu(token)
    return {
        "payload": payload,
        "create_result": create_result,
        "current_menu": current_menu,
    }
