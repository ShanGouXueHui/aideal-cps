from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.partner_share_asset import PartnerShareAsset
from app.models.product import Product
from app.services.partner_material_bundle_config_service import load_partner_material_bundle_rules
from app.services.recommendation_guard_service import allow_proactive_recommend


def _safe_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _clip(text: str | None, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _pick_hot_product(db: Session) -> Product | None:
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
            _safe_int(getattr(row, "sales_volume", 0)),
            _safe_float(getattr(row, "estimated_commission", 0)),
            _safe_int(getattr(row, "id", 0)),
        ),
        reverse=True,
    )
    return rows[0] if rows else None


def _build_direct_url(product: Product) -> str:
    for attr in ("short_url", "product_url", "material_url", "buy_url"):
        value = (getattr(product, attr, None) or "").strip()
        if value:
            return value
    return ""


def _latest_raster_poster_url(db: Session, product: Product) -> str:
    rules = load_partner_material_bundle_rules()
    base_url = (rules.get("base_url") or "").rstrip("/")
    if not base_url:
        return ""

    asset = (
        db.query(PartnerShareAsset)
        .filter(
            PartnerShareAsset.product_id == product.id,
            PartnerShareAsset.poster_svg_path != None,
        )
        .order_by(PartnerShareAsset.id.desc())
        .first()
    )
    if not asset:
        return ""

    poster_path = (getattr(asset, "poster_svg_path", None) or "").strip().lower()
    if not poster_path:
        return ""

    # 当前仓库里大多是 svg；微信公众号图文封面优先使用 raster 图。
    if not poster_path.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return ""

    return f"{base_url}/api/partner/materials/{asset.asset_token}/files/poster"


def _pick_cover_url(db: Session, product: Product) -> str:
    poster_url = _latest_raster_poster_url(db, product)
    if poster_url:
        return poster_url
    return (getattr(product, "image_url", None) or "").strip()


def _build_fact_line(product: Product) -> str:
    sales_volume = _safe_int(getattr(product, "sales_volume", 0))
    price = _safe_float(getattr(product, "price", 0))
    coupon_price = _safe_float(getattr(product, "coupon_price", 0))

    if coupon_price > 0 and price > coupon_price:
        return f"到手参考¥{coupon_price:.2f}，当前比标价省{price - coupon_price:.2f}元"
    if coupon_price > 0:
        return f"到手参考¥{coupon_price:.2f}"
    if price > 0:
        return f"到手参考¥{price:.2f}"
    if sales_volume > 0:
        return f"已有{sales_volume}人下单"
    return "当前综合条件更稳，适合先看"


def _build_social_line(product: Product) -> str:
    sales_volume = _safe_int(getattr(product, "sales_volume", 0))
    title = (getattr(product, "title", None) or "").strip()

    if sales_volume > 0:
        return f"已有{sales_volume}人下单，先看热度更高的通常更不容易踩空"

    if any(token in title for token in ("卫生纸", "抽纸", "纸巾", "洗衣液", "湿巾", "牙膏")):
        return "这类高频消耗品，临时缺了更容易原价补，现在先看更省心"

    return "我先按价格、热度和店铺质量帮你筛过一轮，这款更适合作为第一眼候选"


def get_today_recommend_news_reply(db: Session, wechat_openid: str) -> dict | None:
    product = _pick_hot_product(db)
    if not product:
        return None

    title = f"今日推荐｜{_clip(getattr(product, 'title', ''), 22)}"
    description = f"{_build_fact_line(product)}；{_build_social_line(product)}"
    pic_url = _pick_cover_url(db, product)
    url = _build_direct_url(product)

    if not pic_url or not url:
        return None

    return {
        "reply_type": "news",
        "articles": [
            {
                "title": title,
                "description": _clip(description, 120),
                "pic_url": pic_url,
                "url": url,
            }
        ],
    }


def get_find_product_entry_news_reply(db: Session, wechat_openid: str) -> dict | None:
    product = _pick_hot_product(db)
    if not product:
        return None

    title = f"找商品｜先看这款更热门的"
    description = (
        f"{_build_fact_line(product)}；"
        f"点图直接看商品，也可以直接回复：卫生纸 / 洗衣液 / 宝宝湿巾 / 京东自营"
    )
    pic_url = _pick_cover_url(db, product)
    url = _build_direct_url(product)

    if not pic_url or not url:
        return None

    return {
        "reply_type": "news",
        "articles": [
            {
                "title": title,
                "description": _clip(description, 120),
                "pic_url": pic_url,
                "url": url,
            }
        ],
    }
