from __future__ import annotations

from decimal import Decimal
import re
from typing import Any

from app.services.jd_union_client import (
    JDUnionClient,
    extract_goods_query_items,
    extract_promotion_payload,
)
from app.services.live_search_config_service import load_live_search_rules
from app.services.product_compliance_service import classify_product_compliance


def _pick_image_url(item: dict[str, Any]) -> str | None:
    image_info = item.get("imageInfo") or {}
    if image_info.get("whiteImage"):
        return image_info["whiteImage"]

    image_list = image_info.get("imageList") or []
    if isinstance(image_list, list) and image_list:
        return image_list[0].get("url")
    if isinstance(image_list, dict):
        if image_list.get("url"):
            return image_list.get("url")
        url_info = image_list.get("urlInfo")
        if isinstance(url_info, dict):
            return url_info.get("url")
    return item.get("imageUrl")


def _pick_category_name(item: dict[str, Any]) -> str | None:
    category_info = item.get("categoryInfo") or {}
    return (
        category_info.get("cid3Name")
        or category_info.get("cid2Name")
        or category_info.get("cid1Name")
    )


def _pick_shop_name(item: dict[str, Any]) -> str | None:
    shop_info = item.get("shopInfo") or {}
    return item.get("shopName") or shop_info.get("shopName")


def _pick_material_url(item: dict[str, Any]) -> str | None:
    material_url = item.get("materialUrl")
    if material_url:
        if str(material_url).startswith("http"):
            return material_url
        return f"https://{material_url}"

    sku_id = item.get("skuId")
    if sku_id:
        return f"https://item.m.jd.com/product/{sku_id}.html"
    return None


def _extract_sku_id_from_material_url(material_url: str | None) -> str | None:
    text = str(material_url or "")
    m = re.search(r"/product/(\d+)\.html", text)
    if m:
        return m.group(1)
    m = re.search(r"/(\d+)\.html", text)
    if m:
        return m.group(1)
    return None


def _pick_jd_sku_id(item: dict[str, Any], material_url: str | None) -> str:
    for key in ("skuId", "wareId", "spuid"):
        value = item.get(key)
        if value is not None and str(value).strip().isdigit():
            return str(value).strip()

    parsed = _extract_sku_id_from_material_url(material_url)
    if parsed:
        return parsed

    for key in ("itemId", "oriItemId", "callerItemId"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    return str(material_url or "")


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _build_reason(row: dict[str, Any]) -> str:
    coupon_price = _to_decimal(row.get("coupon_price"))
    price = _to_decimal(row.get("price"))
    sales_volume = _to_int(row.get("sales_volume"))
    if coupon_price > 0 and price > coupon_price:
        return f"当前券后比标价便宜{(price - coupon_price):.2f}元，价格更实惠"
    if sales_volume > 0:
        return f"已有{sales_volume}人下单，热度更高"
    return "当前关键词实时检索命中，适合直接看看"


def _normalize_live_item(item: dict[str, Any], short_url: str | None = None) -> dict[str, Any]:
    price_info = item.get("priceInfo") or {}
    commission_info = item.get("commissionInfo") or {}
    shop_info = item.get("shopInfo") or {}
    forbid_types = item.get("forbidTypes") or []

    material_url = _pick_material_url(item)
    title = item.get("skuName") or item.get("wareName") or item.get("name") or "未知商品"
    category_name = _pick_category_name(item)
    shop_name = _pick_shop_name(item)

    meta = classify_product_compliance(
        title=title,
        category_name=category_name,
        shop_name=shop_name,
        forbid_types=forbid_types,
    )

    coupon_price = _to_decimal(
        price_info.get("lowestCouponPrice")
        or price_info.get("lowestPrice")
        or price_info.get("price")
        or 0
    )
    price = _to_decimal(price_info.get("price") or coupon_price or 0)
    sales_volume = _to_int(item.get("inOrderCount30DaysSku") or item.get("inOrderCount30Days"))

    return {
        "source": "jd_live",
        "jd_sku_id": _pick_jd_sku_id(item, material_url),
        "title": title,
        "image_url": _pick_image_url(item),
        "material_url": material_url,
        "short_url": short_url,
        "product_url": short_url or material_url,
        "category_name": category_name,
        "shop_name": shop_name,
        "shop_id": str(shop_info.get("shopId")) if shop_info.get("shopId") is not None else None,
        "price": float(price),
        "coupon_price": float(coupon_price),
        "commission_rate": _to_float(commission_info.get("commissionShare")),
        "estimated_commission": _to_float(commission_info.get("commission")),
        "sales_volume": sales_volume,
        "merchant_health_score": None,
        "merchant_recommendable": True,
        "elite_name": None,
        "owner": item.get("owner"),
        "reason": _build_reason({
            "coupon_price": coupon_price,
            "price": price,
            "sales_volume": sales_volume,
        }),
        "compliance_level": meta["compliance_level"],
        "age_gate_required": meta["age_gate_required"],
        "allow_proactive_push": meta["allow_proactive_push"],
        "allow_partner_share": meta["allow_partner_share"],
        "compliance_notes": meta["compliance_notes"],
    }


def _build_short_link(client: JDUnionClient, material_url: str | None) -> str | None:
    if not material_url:
        return None
    try:
        response = client.promotion_bysubunionid_get(material_id=material_url, chain_type=2, scene_id=1)
        payload = extract_promotion_payload(response)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        if isinstance(data, dict):
            return data.get("shortURL") or data.get("clickURL")
    except Exception:
        return None
    return None


def search_live_jd_products(
    *,
    query_text: str,
    jd_client: JDUnionClient | None = None,
    adult_verified: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    rules = load_live_search_rules()
    if not rules.get("enabled", True):
        return []

    client = jd_client or JDUnionClient()
    page_size = limit or int(rules["live_page_size"])

    response = client.goods_query(
        keyword=query_text,
        page_index=1,
        page_size=page_size,
        sort_name=rules.get("default_sort_name"),
        sort=rules.get("default_sort"),
    )
    items = extract_goods_query_items(response)

    normalized: list[dict[str, Any]] = []
    for item in items:
        material_url = _pick_material_url(item)
        short_url = _build_short_link(client, material_url)
        row = _normalize_live_item(item, short_url=short_url)

        if row["compliance_level"] == "hard_block":
            continue
        if not adult_verified and row["compliance_level"] != "normal":
            continue

        normalized.append(row)

    normalized.sort(
        key=lambda x: (
            -(x.get("sales_volume") or 0),
            -(x.get("commission_rate") or 0),
            x.get("coupon_price") or x.get("price") or 0,
        )
    )
    return normalized[: int(rules["live_keep_top_n"])]
