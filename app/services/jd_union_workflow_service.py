from __future__ import annotations

from typing import Any

from app.services.jd_union_client import (
    JDUnionClient,
    extract_jingfen_items,
    extract_promotion_payload,
)


class JDUnionWorkflowService:
    def __init__(self, client: JDUnionClient | None = None) -> None:
        self.client = client or JDUnionClient()

    def query_goods(
        self,
        *,
        elite_id: int,
        page_index: int = 1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        response = self.client.jingfen_query(
            elite_id=elite_id,
            page_index=page_index,
            page_size=page_size,
        )
        return extract_jingfen_items(response)

    def build_short_link(self, material_id: str) -> str | None:
        response = self.client.promotion_bysubunionid_get(
            material_id=material_id,
            chain_type=2,
            scene_id=1,
        )
        payload = extract_promotion_payload(response)
        if not isinstance(payload, dict):
            return None

        data = payload.get("data", {})
        if isinstance(data, dict):
            return data.get("shortURL") or data.get("clickURL")
        return None

    def query_goods_with_links(
        self,
        *,
        elite_id: int,
        limit: int = 5,
        page_index: int = 1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        goods = self.query_goods(
            elite_id=elite_id,
            page_index=page_index,
            page_size=page_size,
        )

        result: list[dict[str, Any]] = []
        for item in goods[:limit]:
            material_id = item.get("materialUrl")
            short_url = self.build_short_link(material_id) if material_id else None

            result.append(
                {
                    "skuName": item.get("skuName"),
                    "brandName": item.get("brandName"),
                    "materialUrl": material_id,
                    "shortURL": short_url,
                    "price": (item.get("priceInfo") or {}).get("price"),
                    "lowestCouponPrice": (item.get("priceInfo") or {}).get("lowestCouponPrice"),
                    "commission": (item.get("commissionInfo") or {}).get("commission"),
                    "commissionShare": (item.get("commissionInfo") or {}).get("commissionShare"),
                    "eliteId": ((item.get("resourceInfo") or {}).get("eliteId")),
                    "eliteName": ((item.get("resourceInfo") or {}).get("eliteName")),
                }
            )
        return result
