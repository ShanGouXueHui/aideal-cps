from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy.orm import Session

from app.models.click_log import ClickLog
from app.models.product import Product
from app.models.user import User
from app.services.jd_union_workflow_service import JDUnionWorkflowService


def _truncate(value: str | None, max_len: int) -> str | None:
    if not value:
        return None
    return value[:max_len]


def _get_or_create_user(db: Session, wechat_openid: str) -> User:
    user = db.query(User).filter(User.wechat_openid == wechat_openid).first()
    if user:
        return user

    while True:
        subunionid = "wx_" + secrets.token_hex(8)
        exists = db.query(User).filter(User.subunionid == subunionid).first()
        if not exists:
            break

    user = User(
        wechat_openid=wechat_openid,
        nickname=None,
        subunionid=subunionid,
        wechat_unionid=None,
    )
    db.add(user)
    db.flush()
    return user


def _resolve_final_url(db: Session, product: Product) -> str:
    if getattr(product, "short_url", None):
        return product.short_url
    if getattr(product, "product_url", None):
        return product.product_url
    if getattr(product, "material_url", None):
        workflow = JDUnionWorkflowService()
        short_url = workflow.build_short_link(product.material_url)
        if short_url:
            product.short_url = short_url
            product.product_url = short_url
            db.flush()
            return short_url
        return product.material_url
    raise ValueError("No available promotion url for product")


def create_click_redirect(
    db: Session,
    *,
    wechat_openid: str,
    product_id: int,
    scene: str | None,
    slot: int | None,
    request_source: str,
    client_ip: str | None,
    user_agent: str | None,
    referer: str | None,
) -> dict[str, Any]:
    user = _get_or_create_user(db, wechat_openid)

    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.status == "active")
        .first()
    )
    if not product:
        raise ValueError("Product not found")

    final_url = _resolve_final_url(db, product)
    trace_id = secrets.token_hex(12)

    click_log = ClickLog(
        user_id=user.id,
        product_id=product.id,
        subunionid=user.subunionid,
        wechat_openid=wechat_openid,
        request_source=request_source,
        scene=scene,
        slot=slot,
        trace_id=trace_id,
        promotion_url=final_url,
        final_url=final_url,
        material_url=getattr(product, "material_url", None),
        short_url=getattr(product, "short_url", None),
        client_ip=_truncate(client_ip, 64),
        user_agent=_truncate(user_agent, 500),
        referer=_truncate(referer, 1000),
    )
    db.add(click_log)
    db.commit()
    db.refresh(click_log)

    return {
        "trace_id": trace_id,
        "click_log_id": click_log.id,
        "final_url": final_url,
        "user_id": user.id,
        "product_id": product.id,
        "subunionid": user.subunionid,
        "scene": scene,
        "slot": slot,
    }
