from app.services.wechat_service import build_text_response
from app.services.user_service import get_or_create_user_by_openid
from app.services.recommendation_service import generate_reason
from app.core.db import SessionLocal
from app.models.product import Product

BASE_URL = "http://8.136.28.6"


def build_product_text(product, openid):
    link = f"{BASE_URL}/api/promotion/redirect?wechat_openid={openid}&product_id={product.id}"
    reason = generate_reason(product)

    return f"""【{product.title}】
券后价：{product.coupon_price}
推荐理由：{reason}
👉 点击购买：
{link}"""


def get_products_by_keyword(db, keyword: str, limit: int = 3):
    if keyword == "手机":
        return db.query(Product).filter(
            Product.category_name.like("%手机%"),
            Product.status == "active"
        ).order_by(Product.sales_volume.desc()).limit(limit).all()

    if keyword == "家电":
        return db.query(Product).filter(
            Product.category_name.like("%电%"),
            Product.status == "active"
        ).order_by(Product.sales_volume.desc()).limit(limit).all()

    return []


def route(msg):
    to_user = msg.get("FromUserName")
    from_user = msg.get("ToUserName")
    msg_type = (msg.get("MsgType") or "").lower()

    if to_user:
        get_or_create_user_by_openid(to_user)

    if msg_type == "text":
        content = (msg.get("Content") or "").strip()

        db = SessionLocal()
        try:
            if content in ["手机", "家电"]:
                products = get_products_by_keyword(db, content, limit=3)

                if not products:
                    return build_text_response(to_user, from_user, f"暂无{content}商品")

                text = f"🔥 {content}推荐（Top{len(products)}）\n\n"
                text += "\n\n".join([build_product_text(p, to_user) for p in products])

                return build_text_response(to_user, from_user, text)

        finally:
            db.close()

        return build_text_response(to_user, from_user, "请输入：手机 / 家电")

    return build_text_response(to_user, from_user, "已收到")
