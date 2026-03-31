import hashlib
import json
from datetime import datetime
from typing import Any, Dict
import httpx
from app.core.config import settings


def _format_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sign(params, secret):
    s = secret + "".join(f"{k}{params[k]}" for k in sorted(params)) + secret
    return hashlib.md5(s.encode()).hexdigest().upper()


def build_params(material_id: str):
    biz = {
        "promotionCodeReq": {
            "materialId": material_id,
            "pid": settings.JD_PID
        }
    }

    params = {
        "method": "jd.union.open.selling.promotion.get",
        "app_key": settings.JD_APP_KEY,
        "timestamp": _format_timestamp(),
        "format": "json",
        "v": "1.0",
        "sign_method": "md5",
        "param_json": json.dumps(biz, separators=(",", ":")),
    }

    params["sign"] = _sign(params, settings.JD_APP_SECRET)
    return params


async def request_jd_promotion_link(material_id: str):
    params = build_params(material_id)

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(settings.JD_API_BASE, data=params)
            data = r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

    try:
        raw = data["jd_union_open_selling_promotion_get_responce"]["result"]
        result = json.loads(raw)

        if result.get("code") != 200:
            return {"success": False, "error": result}

        d = result.get("data", {})

        url = d.get("shortURL") or d.get("clickURL")

        return {"success": True, "promotion_url": url, "raw": result}

    except Exception as e:
        return {"success": False, "error": str(e), "raw": data}
