from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.partner_share_entry_config_service import load_partner_share_entry_rules
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
        "buy_qr_svg_path",
        "share_qr_svg_path",
        "poster_svg_path",
        "partner_code",
        "partner_account_id",
        "asset_token",
        "reason",
        "price_text",
        "title",
        "j_command_short",
        "j_command_long",
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


def _fallback_reason(product: Product, price_value: float) -> str:
    if price_value > 0 and _safe_float(product.price) > price_value:
        return f"当前券后比标价便宜{_safe_float(product.price) - price_value:.2f}元，到手价更有优势。"
    if int(product.sales_volume or 0) > 0:
        return f"当前已有{int(product.sales_volume or 0)}人购买，热度更高。"
    return "当前综合条件比较稳，适合先作为分享候选。"


def _append_if(lines: list[str], label: str, value) -> None:
    if value:
        lines.append(f"{label}{value}")


def _build_material_bundle_reply(product: Product, asset: dict) -> str:
    rules = load_partner_share_entry_rules()
    intro = rules.get("intro") or "已帮你生成这件商品的专属分销素材摘要："
    footer_lines = rules.get("footer_lines") or []

    buy_url = asset.get("buy_url") or product.short_url or product.product_url or ""
    share_url = asset.get("share_url") or buy_url
    price_value = _safe_float(product.coupon_price) or _safe_float(product.price)
    reason = asset.get("reason") or _fallback_reason(product, price_value)

    lines = [
        intro,
        "",
        f"商品：{asset.get('title') or product.title}",
        f"店铺：{product.shop_name or '未知店铺'}",
        f"到手参考：¥{price_value:.2f}" if price_value > 0 else "到手参考：以页面为准",
        f"推荐理由：{reason}",
        f"自己先买：{buy_url}" if buy_url else "自己先买：链接生成中",
        f"转发分享：{share_url}" if share_url else "转发分享：链接生成中",
    ]

    _append_if(lines, "合伙人编码：", asset.get("partner_code"))
    _append_if(lines, "素材标识：", asset.get("asset_token"))
    _append_if(lines, "海报路径：", asset.get("poster_svg_path"))
    _append_if(lines, "购买码路径：", asset.get("buy_qr_svg_path"))
    _append_if(lines, "分享码路径：", asset.get("share_qr_svg_path"))

    buy_copy = asset.get("buy_copy")
    share_copy = asset.get("share_copy")
    j_command_short = asset.get("j_command_short")
    j_command_long = asset.get("j_command_long")

    if buy_copy:
        lines.extend(["", "购买文案：", buy_copy])
    if share_copy:
        lines.extend(["", "分享文案：", share_copy])
    if j_command_short or j_command_long:
        lines.append("")
        _append_if(lines, "京口令(短)：", j_command_short)
        _append_if(lines, "京口令(长)：", j_command_long)

    if asset.get("poster_svg_path"):
        lines.append("")
        lines.append("这次已经生成了完整素材包核心信息，你可以直接用于朋友圈/私聊分发。")

    if footer_lines:
        lines.append("")
        lines.extend(footer_lines)

    return "\n".join(lines).strip()


def get_partner_share_product_request_reply(db: Session, wechat_openid: str, content: str | None) -> str | None:
    keyword = parse_share_product_keyword(content)
    if not keyword:
        return None

    product = _search_shareable_product(db, keyword)
    if not product:
        rules = load_partner_share_entry_rules()
        template = rules.get("empty_reply_template") or "当前没有适合直接分享的商品。"
        return template.format(keyword=keyword)

    asset = _generate_partner_asset_payload(db, wechat_openid, int(product.id))
    return _build_material_bundle_reply(product, asset)
