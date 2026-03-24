from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.promotion_service import (
    create_promotion_link,
    create_promotion_link_by_openid,
)

router = APIRouter(prefix="/promotion", tags=["promotion"])


@router.post("/link")
def generate_promotion_link(
    product_id: int,
    user_id: Optional[int] = None,
    wechat_openid: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        if wechat_openid:
            return create_promotion_link_by_openid(
                db=db,
                wechat_openid=wechat_openid,
                product_id=product_id,
            )

        if user_id is not None:
            return create_promotion_link(
                db=db,
                user_id=user_id,
                product_id=product_id,
            )

        raise HTTPException(status_code=400, detail="user_id or wechat_openid is required")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


from fastapi.responses import RedirectResponse


@router.get("/redirect")
def redirect_promotion_link(
    wechat_openid: str,
    product_id: int,
    db: Session = Depends(get_db),
):
    result = create_promotion_link_by_openid(
        db=db,
        wechat_openid=wechat_openid,
        product_id=product_id,
    )
    return RedirectResponse(url=result["promotion_url"])
