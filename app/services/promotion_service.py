from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.product import Product
from app.models.click_log import ClickLog
from app.models.user import User
from app.services.jd_service import get_jd_promotion_link


def _build_promotion_result(click_log, user, product, promotion_url):
    return {
        "message": "promotion link generated successfully",
        "integration_mode": "jd_union_media_real_redirect",
        "site_id": settings.JD_SITE_ID,
        "position_id": settings.JD_POSITION_ID,
        "user_id": user.id,
        "product_id": product.id,
        "subunionid": user.subunionid,
        "promotion_url": promotion_url,
        "click_log_id": click_log.id,
        "is_mock": False,
        "jd_error": None,
        "jd_raw": None,
    }


def create_promotion_link(db: Session, user_id: int, product_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    product = db.query(Product).filter(
        Product.id == product_id,
        Product.status == "active"
    ).first()
    if not product:
        raise ValueError("Product not found")

    promotion_url = get_jd_promotion_link(product.product_url)

    click_log = ClickLog(
        user_id=user.id,
        product_id=product.id,
        subunionid=user.subunionid,
        promotion_url=promotion_url,
    )
    db.add(click_log)
    db.commit()
    db.refresh(click_log)

    return _build_promotion_result(click_log, user, product, promotion_url)


def create_promotion_link_by_openid(db: Session, wechat_openid: str, product_id: int):
    user = db.query(User).filter(User.wechat_openid == wechat_openid).first()
    if not user:
        raise ValueError("User not found")

    product = db.query(Product).filter(
        Product.id == product_id,
        Product.status == "active"
    ).first()
    if not product:
        raise ValueError("Product not found")

    promotion_url = get_jd_promotion_link(product.product_url)

    click_log = ClickLog(
        user_id=user.id,
        product_id=product.id,
        subunionid=user.subunionid,
        promotion_url=promotion_url,
    )
    db.add(click_log)
    db.commit()
    db.refresh(click_log)

    return _build_promotion_result(click_log, user, product, promotion_url)
