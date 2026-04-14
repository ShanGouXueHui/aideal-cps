from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.models.partner_account import PartnerAccount
from app.models.partner_point_redemption import PartnerPointRedemption
from app.services.partner_account_service import enroll_partner_by_openid
from app.services.partner_redemption_catalog_service import (
    get_redemption_item,
    load_partner_redemption_catalog,
)
from app.services.partner_reward_service import (
    get_partner_reward_overview,
    record_partner_reward_event,
)


TWOPLACES = Decimal("0.01")


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _get_partner_account(db: Session, wechat_openid: str) -> PartnerAccount:
    partner_info = enroll_partner_by_openid(db, wechat_openid)
    account = db.query(PartnerAccount).filter(PartnerAccount.id == partner_info["partner_account_id"]).first()
    if not account:
        raise ValueError("Partner account not found")
    return account


def list_partner_redemption_options(db: Session, *, wechat_openid: str) -> dict:
    overview = get_partner_reward_overview(db, wechat_openid=wechat_openid)
    catalog = load_partner_redemption_catalog()
    return {
        "available_points": overview["available_points"],
        "currency_name": overview["point_use_plan"]["currency_name"],
        "items": catalog["items"],
    }


def preview_partner_redemption(
    db: Session,
    *,
    wechat_openid: str,
    item_code: str,
    use_points: Any | None = None,
) -> dict:
    overview = get_partner_reward_overview(db, wechat_openid=wechat_openid)
    item = get_redemption_item(item_code)

    available_points = _to_decimal(overview["available_points"])
    cash_price = _to_decimal(item["cash_price_rmb"])
    point_to_rmb_rate = _to_decimal(item["point_to_rmb_rate"])
    max_points_ratio = _to_decimal(item["max_points_ratio"])

    max_points_by_price = (cash_price * max_points_ratio).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    if use_points is None:
        points_used = min(available_points, max_points_by_price)
    else:
        requested = _to_decimal(use_points)
        if requested < 0:
            raise ValueError("use_points cannot be negative")
        points_used = min(requested, available_points, max_points_by_price)

    cash_offset = (points_used / point_to_rmb_rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    cash_due = (cash_price - cash_offset).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    if cash_due < Decimal("0.00"):
        cash_due = Decimal("0.00")

    if cash_due == Decimal("0.00") and item.get("auto_fulfill_if_fully_offset", False):
        status_hint = "completed"
        fulfill_mode = "points"
    elif cash_due > Decimal("0.00"):
        status_hint = "pending_payment"
        fulfill_mode = "mixed" if points_used > Decimal("0.00") else "cash"
    else:
        status_hint = "pending_payment"
        fulfill_mode = "cash"

    return {
        "item_code": item["item_code"],
        "item_name": item["item_name"],
        "scene_code": item["scene_code"],
        "description": item["description"],
        "cash_price_rmb": float(cash_price),
        "available_points": float(available_points),
        "points_used": float(points_used),
        "cash_due_rmb": float(cash_due),
        "point_to_rmb_rate": float(point_to_rmb_rate),
        "status_hint": status_hint,
        "fulfill_mode": fulfill_mode,
    }


def commit_partner_redemption(
    db: Session,
    *,
    wechat_openid: str,
    item_code: str,
    use_points: Any | None = None,
    note: str | None = None,
) -> dict:
    account = _get_partner_account(db, wechat_openid)
    preview = preview_partner_redemption(
        db,
        wechat_openid=wechat_openid,
        item_code=item_code,
        use_points=use_points,
    )
    item = get_redemption_item(item_code)

    redemption = PartnerPointRedemption(
        partner_account_id=account.id,
        item_code=item["item_code"],
        item_name=item["item_name"],
        scene_code=item["scene_code"],
        cash_price_rmb=_to_decimal(preview["cash_price_rmb"]),
        points_used=_to_decimal(preview["points_used"]),
        cash_due_rmb=_to_decimal(preview["cash_due_rmb"]),
        status=preview["status_hint"],
        fulfill_mode=preview["fulfill_mode"],
        note=note,
    )
    db.add(redemption)
    db.commit()
    db.refresh(redemption)

    ledger_result = None
    if _to_decimal(preview["points_used"]) > Decimal("0.00"):
        ledger_result = record_partner_reward_event(
            db,
            wechat_openid=wechat_openid,
            event_type="redeem",
            points_delta=preview["points_used"],
            note=f"redemption:{item['item_code']}",
        )

    account = db.query(PartnerAccount).filter(PartnerAccount.id == account.id).first()
    if not account:
        raise ValueError("Partner account missing after redemption")

    if item["scene_code"] == "partner_membership_fee" and _to_decimal(preview["cash_due_rmb"]) == Decimal("0.00"):
        account.activation_fee_paid = True
        account.activation_fee_paid_at = datetime.now(timezone.utc)
        account.activated_via = preview["fulfill_mode"]
        if account.activated_at is None:
            account.activated_at = datetime.now(timezone.utc)
        account.last_active_at = datetime.now(timezone.utc)
        redemption.status = "completed"
        redemption.fulfilled_at = datetime.now(timezone.utc)
    elif _to_decimal(preview["cash_due_rmb"]) == Decimal("0.00"):
        redemption.status = "completed"
        redemption.fulfilled_at = datetime.now(timezone.utc)
    else:
        redemption.status = "pending_payment"

    db.commit()
    db.refresh(redemption)
    db.refresh(account)

    return {
        "redemption_id": redemption.id,
        "partner_account_id": account.id,
        "item_code": redemption.item_code,
        "item_name": redemption.item_name,
        "scene_code": redemption.scene_code,
        "cash_price_rmb": float(_to_decimal(redemption.cash_price_rmb)),
        "points_used": float(_to_decimal(redemption.points_used)),
        "cash_due_rmb": float(_to_decimal(redemption.cash_due_rmb)),
        "status": redemption.status,
        "fulfill_mode": redemption.fulfill_mode,
        "activation_fee_paid": bool(account.activation_fee_paid),
        "activated_via": account.activated_via,
        "ledger_result": ledger_result,
    }


def get_partner_redemption_history(
    db: Session,
    *,
    wechat_openid: str,
    limit: int = 20,
) -> dict:
    account = _get_partner_account(db, wechat_openid)
    rows = (
        db.query(PartnerPointRedemption)
        .filter(PartnerPointRedemption.partner_account_id == account.id)
        .order_by(PartnerPointRedemption.id.desc())
        .limit(limit)
        .all()
    )
    items = []
    for row in rows:
        items.append(
            {
                "redemption_id": row.id,
                "item_code": row.item_code,
                "item_name": row.item_name,
                "scene_code": row.scene_code,
                "cash_price_rmb": float(_to_decimal(row.cash_price_rmb)),
                "points_used": float(_to_decimal(row.points_used)),
                "cash_due_rmb": float(_to_decimal(row.cash_due_rmb)),
                "status": row.status,
                "fulfill_mode": row.fulfill_mode,
                "note": row.note,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "fulfilled_at": row.fulfilled_at.isoformat() if row.fulfilled_at else None,
            }
        )
    return {
        "partner_account_id": account.id,
        "activation_fee_paid": bool(account.activation_fee_paid),
        "activated_via": account.activated_via,
        "items": items,
    }
