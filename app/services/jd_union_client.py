from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

import requests
from zoneinfo import ZoneInfo

from app.core.jd_union_config import (
    jd_union_settings,
    parse_pid_for_site_position,
    resolved_position_id,
    resolved_site_id,
)

LOGGER = logging.getLogger(__name__)


def _shanghai_timestamp() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")


def _compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _mask(value: str, keep: int = 4) -> str:
    if not value:
        return value
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}***{value[-keep:]}"


def _redact_params(params: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(params)
    if "app_key" in redacted:
        redacted["app_key"] = _mask(str(redacted["app_key"]))
    if "access_token" in redacted and redacted["access_token"]:
        redacted["access_token"] = _mask(str(redacted["access_token"]))
    if "sign" in redacted:
        redacted["sign"] = _mask(str(redacted["sign"]), keep=6)
    return redacted


class JDUnionClient:
    def __init__(
        self,
        *,
        app_key: str | None = None,
        app_secret: str | None = None,
        base_url: str | None = None,
        access_token: str | None = None,
        timeout_seconds: int | None = None,
        pid: str | None = None,
        site_id: str | None = None,
        position_id: str | None = None,
    ) -> None:
        self.app_key = app_key or jd_union_settings.JD_APP_KEY
        self.app_secret = app_secret or jd_union_settings.JD_APP_SECRET
        self.base_url = base_url or jd_union_settings.JD_API_BASE
        self.access_token = access_token if access_token is not None else jd_union_settings.JD_ACCESS_TOKEN
        self.timeout_seconds = timeout_seconds or jd_union_settings.JD_TIMEOUT_SECONDS
        self.pid = pid or jd_union_settings.JD_PID

        if site_id and position_id:
            self.site_id = site_id
            self.position_id = position_id
        elif self.pid:
            parsed_site_id, parsed_position_id = parse_pid_for_site_position(self.pid)
            self.site_id = site_id or parsed_site_id
            self.position_id = position_id or parsed_position_id
        else:
            self.site_id = site_id or resolved_site_id()
            self.position_id = position_id or resolved_position_id()

        if not self.app_key:
            raise ValueError("JD_APP_KEY is empty")
        if not self.app_secret:
            raise ValueError("JD_APP_SECRET is empty")
        if not self.base_url:
            raise ValueError("JD_API_BASE is empty")

    def _build_sign(self, params: dict[str, Any]) -> str:
        pairs = []
        for key, value in params.items():
            if key == "sign":
                continue
            if value is None or value == "":
                continue
            pairs.append((key, str(value)))
        pairs.sort(key=lambda item: item[0])
        content = "".join(f"{key}{value}" for key, value in pairs)
        raw = f"{self.app_secret}{content}{self.app_secret}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()

    def _build_request_params(
        self,
        method: str,
        business_payload: dict[str, Any],
        *,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "method": method,
            "app_key": self.app_key,
            "timestamp": timestamp or _shanghai_timestamp(),
            "format": "json",
            "v": "1.0",
            "sign_method": "md5",
            "360buy_param_json": _compact_json(business_payload),
        }
        if self.access_token:
            params["access_token"] = self.access_token
        params["sign"] = self._build_sign(params)
        return params

    def request(
        self,
        method: str,
        business_payload: dict[str, Any],
        *,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        params = self._build_request_params(method, business_payload, timestamp=timestamp)
        LOGGER.info("JD request method=%s params=%s", method, _redact_params(params))
        response = requests.get(self.base_url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        LOGGER.info(
            "JD response method=%s top_keys=%s",
            method,
            list(data.keys()) if isinstance(data, dict) else type(data).__name__,
        )
        return data

    def jingfen_query(
        self,
        *,
        elite_id: int,
        page_index: int = 1,
        page_size: int = 20,
        sort_name: str | None = None,
        sort: str | None = None,
        fields: str | None = None,
        extra_goods_req: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        goods_req: dict[str, Any] = {
            "eliteId": elite_id,
            "pageIndex": page_index,
            "pageSize": page_size,
        }
        if self.pid:
            goods_req["pid"] = self.pid
        if sort_name:
            goods_req["sortName"] = sort_name
        if sort:
            goods_req["sort"] = sort
        if fields:
            goods_req["fields"] = fields
        if extra_goods_req:
            goods_req.update(extra_goods_req)
        return self.request("jd.union.open.goods.jingfen.query", {"goodsReq": goods_req})

    def goods_query(
        self,
        *,
        keyword: str,
        page_index: int = 1,
        page_size: int = 20,
        sort_name: str | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        goods_req: dict[str, Any] = {
            "keyword": str(keyword or "").strip(),
            "pageIndex": int(page_index),
            "pageSize": int(page_size),
        }
        if goods_req["keyword"] == "":
            raise ValueError("goods_query keyword is empty")

        sort_name = str(sort_name or "").strip()
        sort = str(sort or "").strip()

        if sort_name:
            goods_req["sortName"] = sort_name
        if sort:
            goods_req["sort"] = sort

        return self.request("jd.union.open.goods.query", {"goodsReq": goods_req})

    def promotion_bysubunionid_get(
        self,
        *,
        material_id: str,
        chain_type: int = 2,
        scene_id: int = 1,
        sub_union_id: str | None = None,
    ) -> dict[str, Any]:
        promotion_req: dict[str, Any] = {
            "materialId": material_id,
            "siteId": self.site_id,
            "positionId": self.position_id,
            "chainType": chain_type,
            "sceneId": scene_id,
        }
        if sub_union_id:
            promotion_req["subUnionId"] = sub_union_id
        return self.request("jd.union.open.promotion.bysubunionid.get", {"promotionCodeReq": promotion_req})


def _extract_list_like_data(query_result: dict[str, Any]) -> list[dict[str, Any]]:
    data = query_result.get("data", [])
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "result", "goodsResp", "queryVo"):
            value = data.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                if "data" in value and isinstance(value["data"], list):
                    return value["data"]
                return [value]
    return []


def extract_jingfen_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    outer = response.get("jd_union_open_goods_jingfen_query_responce", {})
    query_result = outer.get("queryResult", {})
    if isinstance(query_result, str):
        try:
            query_result = json.loads(query_result)
        except json.JSONDecodeError:
            return []
    if not isinstance(query_result, dict):
        return []
    code = query_result.get("code")
    if code not in (200, "200", 0, "0", None):
        return []
    items = _extract_list_like_data(query_result)
    if items:
        return items
    data = query_result.get("data", {})
    if isinstance(data, dict) and "jfGoodsResp" in data and isinstance(data["jfGoodsResp"], dict):
        return [data["jfGoodsResp"]]
    return []


def extract_goods_query_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    outer = response.get("jd_union_open_goods_query_responce", {})
    query_result = outer.get("queryResult", {})
    if isinstance(query_result, str):
        try:
            query_result = json.loads(query_result)
        except json.JSONDecodeError:
            return []
    if not isinstance(query_result, dict):
        return []
    code = query_result.get("code")
    if code not in (200, "200", 0, "0", None):
        return []
    return _extract_list_like_data(query_result)


def extract_promotion_payload(response: dict[str, Any]) -> dict[str, Any]:
    outer = response.get("jd_union_open_promotion_bysubunionid_get_responce", {})
    for key in ("getResult", "queryResult", "result"):
        value = outer.get(key)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        if isinstance(value, dict):
            return value
    return outer
