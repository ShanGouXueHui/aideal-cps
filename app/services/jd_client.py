import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings


def _format_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sign_jd_params(params: Dict[str, Any], app_secret: str) -> str:
    """
    京东风格签名：
    1. 去掉 value 为 None 的参数
    2. 按 key 字典序排序
    3. app_secret + k1v1k2v2... + app_secret
    4. MD5 大写
    """
    items = []
    for key in sorted(params.keys()):
        value = params[key]
        if value is None:
            continue
        items.append(f"{key}{value}")

    sign_string = f"{app_secret}{''.join(items)}{app_secret}"
    return hashlib.md5(sign_string.encode("utf-8")).hexdigest().upper()


def build_jd_promotion_request(
    material_id: str,
    subunionid: str,
    position_id: str,
    site_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    构造京东转链请求参数。
    这里先按通用工程骨架组织，后续如果你的企业账号接口字段有细微差异，再微调。
    """
    biz_content = {
        "promotionCodeReq": {
            "materialId": material_id,
            "siteId": site_id or settings.JD_SITE_ID,
            "positionId": position_id,
            "subUnionId": subunionid,
        }
    }

    params = {
        "method": "jd.union.open.promotion.common.get",
        "app_key": settings.JD_APP_KEY,
        "access_token": "",
        "timestamp": _format_timestamp(),
        "format": "json",
        "v": "1.0",
        "sign_method": "md5",
        "param_json": json.dumps(biz_content, ensure_ascii=False, separators=(",", ":")),
    }

    params["sign"] = _sign_jd_params(params, settings.JD_APP_SECRET)
    return params


async def request_jd_promotion_link(
    material_id: str,
    subunionid: str,
    position_id: str,
    site_id: Optional[str] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    """
    调用京东转链接口。
    返回统一结构：
    {
      "success": bool,
      "promotion_url": str | None,
      "raw": dict | str | None,
      "error": str | None
    }
    """
    params = build_jd_promotion_request(
        material_id=material_id,
        subunionid=subunionid,
        position_id=position_id,
        site_id=site_id,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(settings.JD_API_BASE, data=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {
            "success": False,
            "promotion_url": None,
            "raw": None,
            "error": f"http_error: {str(e)}",
        }

    # 这里做“宽松解析”，因为不同联盟账号/接口版本字段可能略有差异
    candidate_urls = []

    def _walk(obj: Any):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    _walk(v)
                elif isinstance(v, str):
                    key_lower = k.lower()
                    if "url" in key_lower or "click" in key_lower:
                        if v.startswith("http://") or v.startswith("https://"):
                            candidate_urls.append(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)

    if candidate_urls:
        return {
            "success": True,
            "promotion_url": candidate_urls[0],
            "raw": data,
            "error": None,
        }

    return {
        "success": False,
        "promotion_url": None,
        "raw": data,
        "error": "no_promotion_url_found_in_response",
    }


def build_mock_promotion_url(material_id: str, subunionid: str) -> str:
    return f"https://u.jd.com/mock-promo?sku={material_id}&subunionid={subunionid}"


def build_debug_request_preview(material_id: str, subunionid: str, position_id: str) -> Dict[str, Any]:
    params = build_jd_promotion_request(
        material_id=material_id,
        subunionid=subunionid,
        position_id=position_id,
    )
    safe_params = params.copy()
    if "sign" in safe_params:
        safe_params["sign"] = f"{safe_params['sign'][:8]}..."
    return safe_params
