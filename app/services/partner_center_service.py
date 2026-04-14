from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.partner_account import PartnerAccount
from app.models.partner_share_asset import PartnerShareAsset
from app.models.product import Product
from app.services.partner_account_service import enroll_partner_by_openid
from app.services.partner_center_config_service import load_partner_center_rules
from app.services.partner_redemption_service import (
    get_partner_redemption_history,
    list_partner_redemption_options,
)
from app.services.partner_reward_service import get_partner_reward_overview
from app.services.product_compliance_service import apply_product_visibility_filter


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _get_partner_account(db: Session, wechat_openid: str) -> PartnerAccount:
    partner_info = enroll_partner_by_openid(db, wechat_openid)
    account = db.query(PartnerAccount).filter(PartnerAccount.id == partner_info["partner_account_id"]).first()
    if not account:
        raise ValueError("Partner account not found")
    return account


def _recent_assets(db: Session, partner_account_id: int, limit: int) -> list[dict]:
    rows = (
        db.query(PartnerShareAsset)
        .filter(PartnerShareAsset.partner_account_id == partner_account_id)
        .order_by(PartnerShareAsset.id.desc())
        .limit(limit)
        .all()
    )
    items = []
    for row in rows:
        items.append(
            {
                "asset_id": row.id,
                "asset_token": row.asset_token,
                "product_id": row.product_id,
                "buy_url": row.buy_url,
                "share_url": row.share_url,
                "short_url": row.short_url,
                "buy_copy": row.buy_copy,
                "share_copy": row.share_copy,
                "poster_svg_path": row.poster_svg_path,
                "rank_tags": row.rank_tags,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return items


def _recent_shareable_products(db: Session, limit: int) -> list[dict]:
    query = db.query(Product).filter(Product.status == "active")
    query = apply_product_visibility_filter(query, require_partner_share=True)
    rows = query.order_by(Product.updated_at.desc(), Product.id.desc()).limit(limit).all()

    items = []
    for row in rows:
        items.append(
            {
                "product_id": row.id,
                "title": _safe_text(getattr(row, "title", None)),
                "image_url": _safe_text(getattr(row, "image_url", None)),
                "short_url": _safe_text(getattr(row, "short_url", None)),
                "product_url": _safe_text(getattr(row, "product_url", None)),
                "material_url": _safe_text(getattr(row, "material_url", None)),
                "price": _to_float(getattr(row, "price", None)),
                "coupon_price": _to_float(getattr(row, "coupon_price", None)),
                "commission_rate": _to_float(getattr(row, "commission_rate", None)),
                "estimated_commission": _to_float(getattr(row, "estimated_commission", None)),
                "sales_volume": int(getattr(row, "sales_volume", None) or 0),
                "elite_name": _safe_text(getattr(row, "elite_name", None)),
                "shop_name": _safe_text(getattr(row, "shop_name", None)),
                "merchant_recommendable": bool(getattr(row, "merchant_recommendable", True)),
                "compliance_level": _safe_text(getattr(row, "compliance_level", None)),
            }
        )
    return items


def get_partner_center(db: Session, *, wechat_openid: str) -> dict:
    rules = load_partner_center_rules()
    account = _get_partner_account(db, wechat_openid)

    overview = get_partner_reward_overview(db, wechat_openid=wechat_openid)
    options = list_partner_redemption_options(db, wechat_openid=wechat_openid)
    history = get_partner_redemption_history(
        db,
        wechat_openid=wechat_openid,
        limit=int(rules["recent_redemption_limit"]),
    )

    activation_item_code = rules["activation_item_code"]
    activation_item = None
    for item in options["items"]:
        if item["item_code"] == activation_item_code:
            activation_item = item
            break

    activation_required = not bool(account.activation_fee_paid)
    activation_can_use_points = False
    if activation_item:
        activation_can_use_points = float(options["available_points"]) >= float(activation_item["cash_price_rmb"])

    return {
        "profile": {
            "partner_account_id": account.id,
            "partner_code": account.partner_code,
            "status": account.status,
            "tier_code": account.tier_code,
            "share_rate": float(account.share_rate),
            "activation_fee_paid": bool(account.activation_fee_paid),
            "activated_via": account.activated_via,
            "activated_at": account.activated_at.isoformat() if account.activated_at else None,
        },
        "reward_overview": overview,
        "redemption_options": options,
        "redemption_history": history,
        "recent_assets": _recent_assets(
            db,
            partner_account_id=account.id,
            limit=int(rules["recent_assets_limit"]),
        ),
        "recent_shareable_products": _recent_shareable_products(
            db,
            limit=int(rules["recent_products_limit"]),
        ),
        "monetization_closure": {
            "activation_required": activation_required,
            "activation_item_code": activation_item_code,
            "activation_item": activation_item,
            "activation_can_use_points": activation_can_use_points,
            "policy_note": overview["point_use_plan"]["policy_note"],
        },
    }
