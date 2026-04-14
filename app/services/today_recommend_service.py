from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.recommendation_guard_service import allow_proactive_recommend
from app.services.today_recommend_config_service import load_today_recommend_rules


def _safe_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _build_redirect_url(base_url: str, wechat_openid: str, product_id: int, slot: int) -> str:
    return (
        f"{base_url}/api/promotion/redirect"
        f"?wechat_openid={wechat_openid}"
        f"&product_id={product_id}"
        f"&scene=menu_today_recommend"
        f"&slot={slot}"
    )


def _build_reason(product: Product) -> str:
    sales_volume = int(product.sales_volume or 0)
    price = _safe_float(product.price)
    coupon_price = _safe_float(product.coupon_price)

    if coupon_price > 0 and price > coupon_price:
        return f"当前券后比标价便宜{price - coupon_price:.2f}元，价格更实惠"
    if sales_volume > 0:
        return f"已有{sales_volume}人下单，热度更高"
    return "当前价格和综合条件都比较稳，适合先看"


def _pick_products(db: Session, max_items: int) -> list[Product]:
    rows = (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.compliance_level == "normal",
            Product.allow_proactive_push == True,
            Product.merchant_recommendable == True,
        )
        .all()
    )

    rows = [row for row in rows if allow_proactive_recommend(row)]
    rows.sort(
        key=lambda row: (
            int(row.sales_volume or 0),
            _safe_float(row.estimated_commission),
            int(row.id or 0),
        ),
        reverse=True,
    )
    return rows[:max_items]


def get_today_recommend_reply(db: Session, wechat_openid: str) -> str:
    rules = load_today_recommend_rules()
    max_items = int(rules.get("max_items", 3))
    base_url = rules.get("base_url", "").rstrip("/")
    intro = rules.get("intro") or "今天先给你挑 3 个当前商品池里更值的商品："
    empty_reply = rules.get("empty_reply") or "当前还没有可推荐商品。"

    products = _pick_products(db, max_items=max_items)
    if not products:
        return empty_reply

    parts = [intro, ""]
    for idx, product in enumerate(products, start=1):
        title = (product.title or "").strip()
        if len(title) > 28:
            title = title[:28] + "…"

        price_value = _safe_float(product.coupon_price) or _safe_float(product.price)
        reason = _build_reason(product)
        link = _build_redirect_url(base_url, wechat_openid, int(product.id), idx)

        block = [
            f"{idx}.",
            title,
            f"到手参考：¥{price_value:.2f}" if price_value > 0 else "到手参考：以页面为准",
            f"店铺：{product.shop_name or '未知店铺'}",
            f"理由：{reason}",
            f"查看链接：{link}",
        ]
        parts.extend(block)
        parts.append("")

    parts.append("如果你想换成别的品类，直接回复商品名就行。")
    return "\n".join(parts).strip()
