from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.jd_union_cache_service import JDUnionCacheService
from app.services.jd_union_workflow_service import JDUnionWorkflowService

router = APIRouter(prefix="/jd", tags=["jd"])

workflow = JDUnionWorkflowService()
cache = JDUnionCacheService()


class ShortLinkRequest(BaseModel):
    material_id: str


@router.get("/goods/top")
def jd_goods_top(
    elite_id: int = Query(..., description="京粉频道ID，如 129 高佣榜"),
    limit: int = Query(10, ge=1, le=50),
    page_index: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    use_cache: bool = Query(True),
):
    cache_key = f"jd_goods_top:{elite_id}:{limit}:{page_index}:{page_size}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return {"source": "cache", "rows": cached}

    rows = workflow.query_goods(
        elite_id=elite_id,
        page_index=page_index,
        page_size=page_size,
    )[:limit]

    cache.set(cache_key, rows)
    return {"source": "live", "rows": rows}


@router.get("/goods/top-with-links")
def jd_goods_top_with_links(
    elite_id: int = Query(..., description="京粉频道ID，如 129 高佣榜"),
    limit: int = Query(5, ge=1, le=20),
    page_index: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    use_cache: bool = Query(True),
):
    cache_key = f"jd_goods_top_with_links:{elite_id}:{limit}:{page_index}:{page_size}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return {"source": "cache", "rows": cached}

    rows = workflow.query_goods_with_links(
        elite_id=elite_id,
        limit=limit,
        page_index=page_index,
        page_size=page_size,
    )

    cache.set(cache_key, rows)
    return {"source": "live", "rows": rows}


@router.post("/promotion/short-link")
def jd_promotion_short_link(payload: ShortLinkRequest):
    short_url = workflow.build_short_link(payload.material_id)
    if not short_url:
        raise HTTPException(status_code=502, detail="failed to generate short link")
    return {
        "materialId": payload.material_id,
        "shortURL": short_url,
    }


@router.get("/products/sync")
def jd_products_sync():
    return {
        "message": "use /jd/goods/top or /jd/goods/top-with-links instead",
        "status": "deprecated_placeholder"
    }
