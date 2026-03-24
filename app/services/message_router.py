from decimal import Decimal

from app.services.wechat_service import build_text_response
from app.services.user_service import get_or_create_user_by_openid
from app.services.recommendation_service import generate_reason, select_top_product
from app.core.db import SessionLocal
from app.models.product import Product

BASE_URL = "http://8.136.28.6"


def _safe_decimal(value):
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _format_money(value: Decimal) -> str:
    text = f"{value:.2f}"
    return text


def _short_title(title: str, max_len: int = 28) -> str:
    title = (title or "").strip()
    if len(title) <= max_len:
        return title
    return title[: max_len - 1] + "…"


def build_product_text(product, openid):
    link = f"{BASE_URL}/api/promotion/redirect?wechat_openid={openid}&product_id={product.id}"
    reason = generate_reason(product)

    price = _safe_decimal(getattr(product, "price", 0))
    coupon_price = _safe_decimal(
        getattr(product, "coupon_price", None)
        if getattr(product, "coupon_price", None) is not None
        else getattr(product, "price", 0)
    )
    save_money = price - coupon_price
    if save_money < 0:
        save_money = Decimal("0")

    title = _short_title(getattr(product, "title", "优选商品"))

    return f"""🔥 今日优选

🛍 {title}

💰 券后价：¥{_format_money(coupon_price)}
📉 立省：¥{_format_money(save_money)}

🔥 推荐理由：
{reason}

👉 点击立即查看：
{link}"""


def get_products_by_keyword(db, keyword: str, limit: int = 20):
    if keyword == "手机":
        return (
            db.query(Product)
            .filter(
                Product.category_name.like("%手机%"),
                Product.status == "active",
            )
            .order_by(Product.sales_volume.desc())
            .limit(limit)
            .all()
        )

    if keyword == "家电":
        return (
            db.query(Product)
            .filter(
                Product.category_name.like("%电%"),
                Product.status == "active",
            )
            .order_by(Product.sales_volume.desc())
            .limit(limit)
            .all()
        )

    return []


def route(msg):
    to_user = msg.get("FromUserName")
    from_user = msg.get("ToUserName")
    msg_type = (msg.get("MsgType") or "").lower()

    if to_user:
        get_or_create_user_by_openid(to_user)

    if msg_type == "event":
        event = (msg.get("Event") or "").lower()
        if event == "subscribe":
            return build_text_response(
                to_user,
                from_user,
                "欢迎关注〖智省优选〗\n回复：手机 / 家电",
            )
        return ""

    if msg_type == "text":
        content = (msg.get("Content") or "").strip()
        db = SessionLocal()

        try:
            if content in ["手机", "家电"]:
                products = get_products_by_keyword(db, content, limit=20)
                if not products:
                    return build_text_response(to_user, from_user, f"暂无{content}商品，请稍后再试～")

                product = select_top_product(products)
                if not product:
                    return build_text_response(to_user, from_user, f"暂无{content}商品，请稍后再试～")

                print(f"[WECHAT_RECOMMEND] openid={to_user} keyword={content} product_id={product.id}")

                text = build_product_text(product, to_user)
                return build_text_response(to_user, from_user, text)

        finally:
            db.close()

        return build_text_response(to_user, from_user, "请输入：手机 / 家电")

    return build_text_response(to_user, from_user, "已收到")
