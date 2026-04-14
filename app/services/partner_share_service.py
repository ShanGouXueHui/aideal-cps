from __future__ import annotations

import secrets
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.partner_account import PartnerAccount
from app.models.partner_share_asset import PartnerShareAsset
from app.models.partner_share_click import PartnerShareClick
from app.models.product import Product
from app.services.jd_union_client import JDUnionClient, extract_promotion_payload
from app.services.partner_account_service import enroll_partner_by_openid
from app.services.partner_program_config_service import (
    load_partner_program_rules,
    load_partner_share_copy,
)
from app.services.partner_visual_asset_service import build_partner_asset_bundle


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _price_text(product: Product) -> str:
    coupon_price = getattr(product, "coupon_price", None)
    price = getattr(product, "price", None)
    value = coupon_price if coupon_price not in (None, "", 0, Decimal("0")) else price
    try:
        return f"¥{float(value or 0):.2f}"
    except Exception:
        return "¥0.00"


def _build_reason(product: Product) -> str:
    copy_rules = load_partner_share_copy()
    if getattr(product, "coupon_price", None) and getattr(product, "price", None):
        try:
            price = float(product.price or 0)
            coupon_price = float(product.coupon_price or 0)
            if coupon_price < price:
                return "当前券后更便宜，到手价更有优势。"
        except Exception:
            pass

    if getattr(product, "sales_volume", None):
        try:
            sales_volume = int(product.sales_volume or 0)
            if sales_volume > 0:
                return f"当前已有{sales_volume}笔销量，更适合先看。"
        except Exception:
            pass

    return copy_rules["default_reason"]


def _resolve_material_id(product: Product) -> str:
    for field in ("material_url", "product_url", "short_url"):
        value = getattr(product, field, None)
        if value:
            return value
    raise ValueError("Product has no material_url/product_url/short_url")


def _resolve_rank_tags(product: Product, explicit_rank_tags: str | None) -> str | None:
    if explicit_rank_tags:
        return explicit_rank_tags
    candidates = []
    for field in ("ai_tags", "elite_name"):
        value = getattr(product, field, None)
        if value:
            candidates.append(str(value))
    return " | ".join(candidates) if candidates else None


def _truncate(value: str | None, max_len: int) -> str | None:
    if not value:
        return None
    return value[:max_len]


def generate_partner_share_asset(
    db: Session,
    *,
    wechat_openid: str,
    product_id: int,
    rank_tags: str | None = None,
    jd_client: JDUnionClient | None = None,
) -> dict:
    program_rules = load_partner_program_rules()
    copy_rules = load_partner_share_copy()

    partner_info = enroll_partner_by_openid(db, wechat_openid)
    account = db.query(PartnerAccount).filter(PartnerAccount.id == partner_info["partner_account_id"]).first()
    if not account:
        raise ValueError("Partner account not found after enroll")

    product = db.query(Product).filter(Product.id == product_id, Product.status == "active").first()
    if not product:
        raise ValueError("Product not found")

    client = jd_client or JDUnionClient()
    response = client.promotion_bysubunionid_get(
        material_id=_resolve_material_id(product),
        chain_type=3,
        scene_id=1,
        sub_union_id=partner_info["subunionid"],
    )
    payload = extract_promotion_payload(response)
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}

    short_url = data.get("shortURL") or data.get("clickURL") or getattr(product, "short_url", None) or getattr(product, "product_url", None)
    long_url = data.get("clickURL") or short_url
    j_command_short = data.get("jShortCommand")
    j_command_long = data.get("jCommand")

    if not short_url and not long_url:
        raise ValueError("JD promotion link generation failed")

    asset_token = secrets.token_hex(16)
    public_base_url = program_rules["public_base_url"].rstrip("/")
    buy_url = f"{public_base_url}/api/partner/assets/{asset_token}/buy"
    share_url = buy_url
    reason = _build_reason(product)
    price_text = _price_text(product)

    buy_copy = copy_rules["buy_first_template"].format(
        title=_safe_text(getattr(product, "title", "")),
        price_text=price_text,
        reason=reason,
        buy_url=buy_url,
    )
    share_copy = copy_rules["share_template"].format(
        title=_safe_text(getattr(product, "title", "")),
        price_text=price_text,
        reason=reason,
        buy_url=buy_url,
        share_url=share_url,
    )

    asset = PartnerShareAsset(
        partner_account_id=account.id,
        product_id=product.id,
        asset_token=asset_token,
        status="active",
        rank_tags=_resolve_rank_tags(product, rank_tags),
        short_url=short_url,
        long_url=long_url,
        buy_url=buy_url,
        share_url=share_url,
        buy_copy=buy_copy,
        share_copy=share_copy,
        j_command_short=j_command_short,
        j_command_long=j_command_long,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    bundle = build_partner_asset_bundle(
        partner_code=account.partner_code,
        product=product,
        asset_token=asset.asset_token,
        buy_url=asset.buy_url or "",
        share_url=asset.share_url or "",
        buy_copy=asset.buy_copy or "",
        share_copy=asset.share_copy or "",
        reason=reason,
        price_text=price_text,
        rank_tags=asset.rank_tags,
    )

    asset.buy_qr_svg_path = bundle["buy_qr_svg_path"]
    asset.share_qr_svg_path = bundle["share_qr_svg_path"]
    asset.poster_svg_path = bundle["poster_svg_path"]
    db.commit()
    db.refresh(asset)

    return {
        "buy_url": asset.buy_url,
        "share_url": asset.share_url,
        "short_url": asset.short_url,
        "long_url": asset.long_url,
        "buy_copy": asset.buy_copy,
        "share_copy": asset.share_copy,
        "buy_qr_svg_path": asset.buy_qr_svg_path,
        "share_qr_svg_path": asset.share_qr_svg_path,
        "poster_svg_path": asset.poster_svg_path,
        "rank_tags": asset.rank_tags,
        "asset_token": asset.asset_token,
        "partner_code": account.partner_code,
        "partner_account_id": account.id,
        "share_rate": float(account.share_rate),
        "product_id": product.id,
        "title": getattr(product, "title", None),
        "price_text": price_text,
        "reason": reason,
        "j_command_short": asset.j_command_short,
        "j_command_long": asset.j_command_long,
    }


def get_partner_share_asset(db: Session, asset_token: str) -> PartnerShareAsset | None:
    return db.query(PartnerShareAsset).filter(
        PartnerShareAsset.asset_token == asset_token,
        PartnerShareAsset.status == "active",
    ).first()


def open_partner_buy_link(
    db: Session,
    *,
    asset_token: str,
    request_source: str,
    client_ip: str | None,
    user_agent: str | None,
    referer: str | None,
) -> dict:
    asset = get_partner_share_asset(db, asset_token)
    if not asset:
        raise ValueError("Partner asset not found")

    final_url = asset.short_url or asset.long_url
    if not final_url:
        raise ValueError("Partner asset final_url missing")

    click = PartnerShareClick(
        partner_account_id=asset.partner_account_id,
        asset_id=asset.id,
        product_id=asset.product_id,
        request_source=request_source,
        client_ip=_truncate(client_ip, 64),
        user_agent=_truncate(user_agent, 500),
        referer=_truncate(referer, 1000),
    )
    db.add(click)
    db.commit()
    db.refresh(click)

    return {
        "click_id": click.id,
        "asset_id": asset.id,
        "partner_account_id": asset.partner_account_id,
        "product_id": asset.product_id,
        "redirect_url": final_url,
    }
