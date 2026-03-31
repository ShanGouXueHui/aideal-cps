import hashlib
import json
import time
from typing import Any, Dict

import requests

from app.core.config import settings


def build_sign(params: Dict[str, Any], secret: str) -> str:
    raw = secret + "".join(f"{k}{params[k]}" for k in sorted(params.keys())) + secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


def _loads_if_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _extract_url(result_data: Dict[str, Any], fallback_url: str) -> str:
    data = result_data.get("data")
    data = _loads_if_json(data)

    if isinstance(data, list) and data:
        node = data[0]
    elif isinstance(data, dict):
        node = data
    else:
        node = {}

    if not isinstance(node, dict):
        return fallback_url

    for key in ["shortURL", "shortUrl", "clickURL", "clickUrl", "longURL", "longUrl"]:
        value = node.get(key)
        if value:
            return value

    return fallback_url


def build_common_promotion_params(material_id: str) -> Dict[str, Any]:
    param_json = {
        "promotionCodeReq": {
            "materialId": material_id,
            "siteId": str(settings.JD_SITE_ID),
            "positionId": int(settings.JD_POSITION_ID),
            "sceneId": 1,
        }
    }

    params = {
        "method": "jd.union.open.promotion.common.get",
        "app_key": settings.JD_APP_KEY,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "1.0",
        "sign_method": "md5",
        "param_json": json.dumps(param_json, ensure_ascii=False, separators=(",", ":")),
    }
    params["sign"] = build_sign(params, settings.JD_APP_SECRET)
    return params


def get_jd_promotion_link(material_id: str) -> str:
    """
    当前按京东客服答复，仅走通用接口 common.get。
    若失败，回退原始链接，保证主流程不中断。
    """
    if not settings.JD_APP_KEY or not settings.JD_APP_SECRET:
        return material_id

    params = build_common_promotion_params(material_id)

    try:
        resp = requests.post(settings.JD_API_BASE, data=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()

        outer = payload.get("jd_union_open_promotion_common_get_responce", {})
        result_raw = outer.get("getResult") or outer.get("result")
        result_data = _loads_if_json(result_raw)

        if not isinstance(result_data, dict):
            return material_id

        code = str(result_data.get("code", ""))
        if code not in ("200", "0"):
            return material_id

        return _extract_url(result_data, material_id)
    except Exception:
        return material_id
