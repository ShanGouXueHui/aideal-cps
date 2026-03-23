from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.product import Product
from app.models.click_log import ClickLog
from app.models.user import User


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

    promotion_url = product.product_url

    click_log = ClickLog(
        user_id=user.id,
        product_id=product.id,
        subunionid=user.subunionid,
        promotion_url=promotion_url,
    )
    db.add(click_log)
    db.commit()
    db.refresh(click_log)

    return {
        "message": "media promotion link generated successfully",
        "integration_mode": "jd_union_media_manual_redirect",
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
