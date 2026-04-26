from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
import re
import html

from app.core.db import SessionLocal
from app.services.wechat_recommend_runtime_service import (
    get_product_by_id,
    render_more_like_this_h5,
    render_recommend_batch_h5,
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



@router.api_route("/users/test-init", methods=["GET", "POST"], name="h5_user_test_init")
async def h5_user_test_init(
    request: Request,
    wechat_openid: str = Query(default=""),
):
    """Compatibility endpoint for H5 user init."""  # H5_USER_TEST_INIT_COMPAT_GATE
    openid = (
        wechat_openid
        or request.query_params.get("openid")
        or request.query_params.get("wechat_openid")
        or ""
    ).strip()

    if openid:
        db = SessionLocal()
        try:
            from app.services.user_service import get_or_create_user_by_openid_db

            get_or_create_user_by_openid_db(db, openid)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    from app.services.wechat_find_product_entry_config_service import load_find_product_entry_config

    cfg = load_find_product_entry_config()
    response = cfg.get("h5_user_init_response")
    return response if isinstance(response, dict) else {"ok": True}



@router.get("/h5/recommend/batch", name="recommend_batch_page")
async def recommend_batch_page(
    ids: str = Query(default=""),
    focus_id: int = Query(default=0),
    scene: str = Query(default=""),
    slot: str = Query(default=""),
    wechat_openid: str = Query(default=""),
):
    db = SessionLocal()
    try:
        return HTMLResponse(
            render_recommend_batch_h5(
                db,
                ids=ids,
                focus_id=int(focus_id or 0),
                scene=scene,
                slot=slot,
                wechat_openid=wechat_openid,
            )
        )
    finally:
        db.close()


@router.get("/h5/recommend/more-like-this", name="recommend_more_like_this_page")
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


@router.get("/h5/recommend/{product_id}", name="recommend_detail_page")
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

        # First-read price freshness cache: refresh JD price only when stale.
        try:
            from app.services.jd_price_freshness_service import refresh_product_price_if_stale

            product = refresh_product_price_if_stale(db, product, trigger="h5_detail") or product
            db.commit()
            db.refresh(product)
        except Exception:
            db.rollback()

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
