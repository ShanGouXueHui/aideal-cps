from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.core.db import SessionLocal
from app.services.promotion_service import create_promotion_link_by_openid

router = APIRouter()
logger = logging.getLogger(__name__)


def _call_create_promotion_link(
    *,
    wechat_openid: str,
    product_id: int,
    scene: Optional[str],
    slot: Optional[int],
) -> dict:
    db = SessionLocal()
    try:
        return create_promotion_link_by_openid(
            db=db,
            wechat_openid=wechat_openid,
            product_id=product_id,
            scene=scene,
            slot=slot,
        )
    finally:
        db.close()


@router.get("/promotion/link")
def create_promotion_link(
    wechat_openid: str,
    product_id: int,
    scene: Optional[str] = None,
    slot: Optional[int] = None,
):
    try:
        return _call_create_promotion_link(
            wechat_openid=wechat_openid,
            product_id=product_id,
            scene=scene,
            slot=slot,
        )
    except Exception as e:
        logger.exception(
            "promotion link failed | openid=%s product_id=%s scene=%s slot=%s",
            wechat_openid,
            product_id,
            scene,
            slot,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/promotion/redirect")
def promotion_redirect(
    wechat_openid: str = Query(...),
    product_id: int = Query(...),
    scene: Optional[str] = Query(None),
    slot: Optional[int] = Query(None),
):
    try:
        result = _call_create_promotion_link(
            wechat_openid=wechat_openid,
            product_id=product_id,
            scene=scene,
            slot=slot,
        )

        redirect_url = (
            result.get("short_url")
            or result.get("promotion_url")
            or result.get("click_url")
            or result.get("long_url")
            or result.get("material_url")
            or result.get("product_url")
            or result.get("final_url")
        )

        if not redirect_url:
            logger.error(
                "promotion redirect missing url | openid=%s product_id=%s scene=%s slot=%s payload=%s",
                wechat_openid,
                product_id,
                scene,
                slot,
                result,
            )
            raise HTTPException(status_code=404, detail="promotion url not found")

        return RedirectResponse(url=str(redirect_url), status_code=302)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "promotion redirect failed | openid=%s product_id=%s scene=%s slot=%s",
            wechat_openid,
            product_id,
            scene,
            slot,
        )
        raise HTTPException(status_code=500, detail=str(e))
