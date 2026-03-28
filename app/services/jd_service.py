import hashlib
import json
import time
from typing import Any, Dict, Optional

import requests

from app.core.config import settings


def build_sign(params: Dict[str, Any], secret: str) -> str:
    keys = sorted(params.keys())
    raw = secret + "".join(f"{k}{params[k]}" for k in keys) + secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


def _loads_if_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _extract_promotion_url(result_data: Dict[str, Any], fallback_url: str) -> str:
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

    for key in [
        "shortURL",
        "shortUrl",
        "clickURL",
        "clickUrl",
        "longURL",
        "longUrl",
    ]:
        value = node.get(key)
        if value:
            return value

    return fallback_url


def get_jd_promotion_link(material_url: str) -> str:
    """
    京东联盟通用转链接口：
    jd.union.open.promotion.common.get

    返回：
    - 成功：京东推广链接
    - 失败：原始 material_url
    """
    if not settings.JD_APP_KEY or not settings.JD_APP_SECRET:
        return material_url

    param_json = {
        "promotionCodeReq": {
            "materialId": material_url,
            "siteId": settings.JD_SITE_ID,
            "positionId": settings.JD_POSITION_ID,
            "sceneId": 2,
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

    try:
        resp = requests.get(settings.JD_API_BASE, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        outer = data.get("jd_union_open_promotion_common_get_responce", {})
        result_raw = outer.get("result")
        result_data = _loads_if_json(result_raw)

        if not isinstance(result_data, dict):
            return material_url

        code = str(result_data.get("code", ""))
        if code not in ("200", "0"):
            return material_url

        return _extract_promotion_url(result_data, material_url)

    except Exception:
        return material_url
