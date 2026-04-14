from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.recommendation_guard_service import allow_partner_share


def _safe_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def parse_share_product_keyword(content: str | None) -> str | None:
    text = (content or "").strip()
    if not text.startswith("分享商品"):
        return None

    keyword = text[len("分享商品"):].strip()
    for prefix in ("：", ":", "-", "—", "|", "｜", "，", ","):
        if keyword.startswith(prefix):
            keyword = keyword[len(prefix):].strip()

    return keyword or None


def _search_shareable_product(db: Session, keyword: str) -> Product | None:
    rows = (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.compliance_level == "normal",
            Product.allow_partner_share == True,
            Product.merchant_recommendable == True,
            or_(
                Product.title.ilike(f"%{keyword}%"),
                Product.category_name.ilike(f"%{keyword}%"),
                Product.shop_name.ilike(f"%{keyword}%"),
            ),
        )
        .all()
    )

    rows = [row for row in rows if allow_partner_share(row)]
    rows.sort(
        key=lambda row: (
            int(row.sales_volume or 0),
            _safe_float(row.estimated_commission),
            int(row.id or 0),
        ),
        reverse=True,
    )
    return rows[0] if rows else None


def _asset_to_dict(asset) -> dict:
    if asset is None:
        return {}
    if isinstance(asset, dict):
        return asset

    data = {}
    for key in (
        "buy_url",
        "share_url",
        "short_url",
        "long_url",
        "buy_copy",
        "share_copy",
        "partner_code",
        "asset_token",
        "reason",
        "price_text",
        "poster_svg_path",
        "title",
    ):
        if hasattr(asset, key):
            data[key] = getattr(asset, key)
    return data


def _generate_partner_asset_payload(db: Session, wechat_openid: str, product_id: int) -> dict:
    try:
        from app.services.partner_share_service import generate_partner_share_asset
    except Exception:
        return {}

    attempts = [
        lambda: generate_partner_share_asset(db=db, wechat_openid=wechat_openid, product_id=product_id),
        lambda: generate_partner_share_asset(db=db, wechat_openid=wechat_openid, product_id=product_id, jd_client=None),
        lambda: generate_partner_share_asset(db, wechat_openid=wechat_openid, product_id=product_id),
        lambda: generate_partner_share_asset(db, wechat_openid, product_id),
    ]

    for fn in attempts:
        try:
            return _asset_to_dict(fn())
        except TypeError:
            continue
        except Exception:
            break

    return {}


def get_partner_share_product_request_reply(db: Session, wechat_openid: str, content: str | None) -> str | None:
    keyword = parse_share_product_keyword(content)
    if not keyword:
        return None

    product = _search_shareable_product(db, keyword)
    if not product:
        return (
            f"我先按“{keyword}”帮你查了一轮，但当前商品池里还没有找到适合直接分享的结果。\n"
            "你可以换个更直接的商品名再试一次，例如：牙膏、洗衣液、抽纸。"
        )

    asset = _generate_partner_asset_payload(db, wechat_openid, int(product.id))

    buy_url = asset.get("buy_url") or product.short_url or product.product_url or ""
    share_url = asset.get("share_url") or buy_url
    price_value = _safe_float(product.coupon_price) or _safe_float(product.price)

    if asset.get("reason"):
        reason = asset["reason"]
    elif price_value > 0 and _safe_float(product.price) > price_value:
        reason = f"当前券后比标价便宜{_safe_float(product.price) - price_value:.2f}元，到手价更有优势。"
    elif int(product.sales_volume or 0) > 0:
        reason = f"当前已有{int(product.sales_volume or 0)}人购买，热度更高。"
    else:
        reason = "当前综合条件比较稳，适合先作为分享候选。"

    lines = [
        "已帮你生成这件商品的分享摘要：",
        "",
        f"商品：{asset.get('title') or product.title}",
        f"店铺：{product.shop_name or '未知店铺'}",
        f"到手参考：¥{price_value:.2f}" if price_value > 0 else "到手参考：以页面为准",
        f"推荐理由：{reason}",
        f"自己先买：{buy_url}" if buy_url else "自己先买：链接生成中",
        f"转发分享：{share_url}" if share_url else "转发分享：链接生成中",
    ]

    poster_svg_path = asset.get("poster_svg_path")
    if poster_svg_path:
        lines.append("专属素材已生成，可继续用于朋友圈/私聊分发。")

    lines.extend([
        "",
        "你也可以继续回复“分享商品 + 商品名”，例如：",
        "分享商品 洗衣液",
    ])
    return "\n".join(lines)
