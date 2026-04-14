from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.partner_account_service import enroll_partner_by_openid
from app.services.partner_center_service import get_partner_center
from app.services.partner_redemption_service import (
    commit_partner_redemption,
    get_partner_redemption_history,
    list_partner_redemption_options,
    preview_partner_redemption,
)
from app.services.partner_reward_service import get_partner_reward_overview
from app.services.partner_share_service import (
    generate_partner_share_asset,
    get_partner_share_asset,
    open_partner_buy_link,
)

router = APIRouter(prefix="/partner", tags=["partner"])


@router.post("/enroll")
def enroll_partner(wechat_openid: str, db: Session = Depends(get_db)):
    try:
        return enroll_partner_by_openid(db, wechat_openid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/center")
def partner_center(wechat_openid: str, db: Session = Depends(get_db)):
    try:
        return get_partner_center(db, wechat_openid=wechat_openid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/overview")
def partner_overview(wechat_openid: str, db: Session = Depends(get_db)):
    try:
        return get_partner_reward_overview(db, wechat_openid=wechat_openid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/redemption/options")
def redemption_options(wechat_openid: str, db: Session = Depends(get_db)):
    try:
        return list_partner_redemption_options(db, wechat_openid=wechat_openid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/redemption/preview")
def redemption_preview(wechat_openid: str, item_code: str, use_points: float | None = None, db: Session = Depends(get_db)):
    try:
        return preview_partner_redemption(
            db,
            wechat_openid=wechat_openid,
            item_code=item_code,
            use_points=use_points,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/redemption/commit")
def redemption_commit(wechat_openid: str, item_code: str, use_points: float | None = None, note: str | None = None, db: Session = Depends(get_db)):
    try:
        return commit_partner_redemption(
            db,
            wechat_openid=wechat_openid,
            item_code=item_code,
            use_points=use_points,
            note=note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/redemption/history")
def redemption_history(wechat_openid: str, limit: int = 20, db: Session = Depends(get_db)):
    try:
        return get_partner_redemption_history(db, wechat_openid=wechat_openid, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/assets/generate")
def generate_asset(
    wechat_openid: str,
    product_id: int,
    rank_tags: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        return generate_partner_share_asset(
            db,
            wechat_openid=wechat_openid,
            product_id=product_id,
            rank_tags=rank_tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/assets/{asset_token}")
def get_asset(asset_token: str, db: Session = Depends(get_db)):
    asset = get_partner_share_asset(db, asset_token)
    if not asset:
        raise HTTPException(status_code=404, detail="Partner asset not found")
    return {
        "asset_token": asset.asset_token,
        "buy_url": asset.buy_url,
        "share_url": asset.share_url,
        "short_url": asset.short_url,
        "long_url": asset.long_url,
        "buy_copy": asset.buy_copy,
        "share_copy": asset.share_copy,
        "buy_qr_svg_path": asset.buy_qr_svg_path,
        "share_qr_svg_path": asset.share_qr_svg_path,
        "poster_svg_path": asset.poster_svg_path,
        "j_command_short": asset.j_command_short,
        "j_command_long": asset.j_command_long,
        "rank_tags": asset.rank_tags,
        "product_id": asset.product_id,
    }


@router.get("/assets/{asset_token}/buy")
def partner_buy(asset_token: str, request: Request, db: Session = Depends(get_db)):
    try:
        result = open_partner_buy_link(
            db,
            asset_token=asset_token,
            request_source="partner_buy",
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
        )
        return RedirectResponse(url=result["redirect_url"], status_code=302)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
