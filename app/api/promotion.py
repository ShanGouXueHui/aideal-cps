from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.promotion_service import create_promotion_link_by_openid

router = APIRouter(prefix="/promotion", tags=["promotion"])


@router.post("/link")
def generate_promotion_link(
    product_id: int,
    wechat_openid: str,
    scene: Optional[str] = None,
    slot: Optional[int] = None,
    db: Session = Depends(get_db),
):
    try:
        return create_promotion_link_by_openid(
            db=db,
            wechat_openid=wechat_openid,
            product_id=product_id,
            scene=scene,
            slot=slot,
            request_source="promotion_link_api",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/redirect")
def redirect_promotion_link(
    request: Request,
    wechat_openid: str = Query(...),
    product_id: int = Query(...),
    scene: Optional[str] = Query(None),
    slot: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        result = create_promotion_link_by_openid(
            db=db,
            wechat_openid=wechat_openid,
            product_id=product_id,
            scene=scene,
            slot=slot,
            request_source="wechat_redirect",
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
        )
        return RedirectResponse(url=result["final_url"], status_code=302)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
