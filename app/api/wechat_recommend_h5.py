from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
import re
import html

from app.core.db import SessionLocal
from app.services.wechat_recommend_runtime_service import (
    get_product_by_id,
    render_more_like_this_h5,
    render_product_h5,
)


def _normalize_title_tags(content: str) -> str:
    raw = content or ""

    def _fix(match):
        title = html.escape(html.unescape(match.group(1) or ""), quote=True)
        return f"<title>{title}</title>"

    return re.sub(
        r"<title>(.*?)</title>",
        _fix,
        raw,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )

router = APIRouter()


@router.get("/api/h5/recommend/more-like-this", name="recommend_more_like_this_page")
async def recommend_more_like_this_page(
    product_id: int,
    scene: str = Query(default=""),
    slot: str = Query(default=""),
    wechat_openid: str = Query(default=""),
):
    db = SessionLocal()
    try:
        return HTMLResponse(
            render_more_like_this_h5(
                db,
                product_id=int(product_id),
                scene=scene,
                slot=slot,
                wechat_openid=wechat_openid,
            )
        )
    finally:
        db.close()


@router.get("/api/h5/recommend/{product_id}", name="recommend_detail_page")
async def recommend_detail_page(
    product_id: int,
    scene: str = Query(default=""),
    slot: str = Query(default=""),
    wechat_openid: str = Query(default=""),
):
    db = SessionLocal()
    try:
        product = get_product_by_id(db, int(product_id))
        if not product:
            return HTMLResponse("<h3>商品不存在</h3>", status_code=404)
        return HTMLResponse(
            render_product_h5(
                product,
                scene=scene,
                slot=slot,
                wechat_openid=wechat_openid,
            )
        )
    finally:
        db.close()
