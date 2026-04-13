from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.click_redirect_service import create_click_redirect


def create_promotion_link(
    db: Session,
    user_id: int,
    product_id: int,
):
    raise NotImplementedError("Current flow should use create_promotion_link_by_openid")


def create_promotion_link_by_openid(
    db: Session,
    wechat_openid: str,
    product_id: int,
    *,
    scene: str | None = None,
    slot: int | None = None,
    request_source: str = "promotion_api",
    client_ip: str | None = None,
    user_agent: str | None = None,
    referer: str | None = None,
):
    return create_click_redirect(
        db,
        wechat_openid=wechat_openid,
        product_id=product_id,
        scene=scene,
        slot=slot,
        request_source=request_source,
        client_ip=client_ip,
        user_agent=user_agent,
        referer=referer,
    )
