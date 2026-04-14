from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.partner_account import PartnerAccount
from app.models.partner_reward_ledger import PartnerRewardLedger
from app.services.partner_account_service import enroll_partner_by_openid
from app.services.partner_program_config_service import load_partner_program_rules
from app.services.partner_reward_config_service import load_partner_reward_rules


TWOPLACES = Decimal("0.01")


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _abs_decimal(value: Any) -> Decimal:
    return abs(_to_decimal(value))


def _get_partner_account_by_openid(db: Session, wechat_openid: str) -> PartnerAccount:
    partner_info = enroll_partner_by_openid(db, wechat_openid)
    account = db.query(PartnerAccount).filter(PartnerAccount.id == partner_info["partner_account_id"]).first()
    if not account:
        raise ValueError("Partner account not found")
    return account


def _highest_tier_for_commission(lifetime_settled_commission: Decimal) -> tuple[str, float]:
    rules = load_partner_program_rules()
    tiers = rules["tiers"]

    selected_code = rules["default_tier"]
    selected_rate = float(tiers[selected_code]["share_rate"])

    items = sorted(
        tiers.items(),
        key=lambda kv: Decimal(str(kv[1]["settled_commission_threshold"]))
    )
    for code, payload in items:
        threshold = Decimal(str(payload["settled_commission_threshold"]))
        if lifetime_settled_commission >= threshold:
            selected_code = code
            selected_rate = float(payload["share_rate"])

    return selected_code, selected_rate


def _get_lifetime_settled_commission(db: Session, partner_account_id: int) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(PartnerRewardLedger.commission_amount), 0))
        .filter(
            PartnerRewardLedger.partner_account_id == partner_account_id,
            PartnerRewardLedger.event_type == "settled",
        )
        .scalar()
    )
    return _to_decimal(total)


def _apply_tier_upgrade(db: Session, account: PartnerAccount) -> Decimal:
    lifetime_settled_commission = _get_lifetime_settled_commission(db, account.id)
    tier_code, share_rate = _highest_tier_for_commission(lifetime_settled_commission)
    account.tier_code = tier_code
    account.share_rate = share_rate
    return lifetime_settled_commission


def _calc_reward_base(commission_amount: Decimal, applied_share_rate: float) -> Decimal:
    rules = load_partner_reward_rules()
    tax_reserve_rate = Decimal(str(rules["tax_reserve_rate"]))
    points_value_rate = Decimal(str(rules["points_value_rate"]))
    return (commission_amount * tax_reserve_rate * Decimal(str(applied_share_rate)) * points_value_rate).quantize(
        TWOPLACES, rounding=ROUND_HALF_UP
    )


def record_partner_reward_event(
    db: Session,
    *,
    wechat_openid: str,
    event_type: str,
    commission_amount: Any = 0,
    order_ref: str | None = None,
    product_id: int | None = None,
    click_id: int | None = None,
    note: str | None = None,
    points_delta: Any | None = None,
    applied_share_rate: float | None = None,
) -> dict:
    rules = load_partner_reward_rules()
    allowed = set(rules["event_types"])
    if event_type not in allowed:
        raise ValueError(f"Unsupported event_type: {event_type}")

    account = _get_partner_account_by_openid(db, wechat_openid)

    event_share_rate = float(applied_share_rate if applied_share_rate is not None else account.share_rate)
    commission = _to_decimal(commission_amount)
    reward_base = Decimal("0.00")
    points = Decimal("0.00")

    if event_type == "estimated":
        commission = _abs_decimal(commission)
        reward_base = _calc_reward_base(commission, event_share_rate)
        points = Decimal("0.00")

    elif event_type == "settled":
        commission = _abs_decimal(commission)
        reward_base = _calc_reward_base(commission, event_share_rate)
        points = reward_base
        account.cumulative_settled_commission = _to_decimal(account.cumulative_settled_commission) + commission
        account.cumulative_reward_points = _to_decimal(account.cumulative_reward_points) + points

    elif event_type == "reversed":
        commission = -_abs_decimal(commission)
        reward_base = -_calc_reward_base(abs(commission), event_share_rate)
        points = reward_base
        account.cumulative_settled_commission = _to_decimal(account.cumulative_settled_commission) + commission
        account.cumulative_reward_points = _to_decimal(account.cumulative_reward_points) + points

    elif event_type == "redeem":
        commission = Decimal("0.00")
        reward_base = Decimal("0.00")
        if points_delta is None:
            raise ValueError("points_delta is required for redeem")
        points = -_abs_decimal(points_delta)
        account.cumulative_reward_points = _to_decimal(account.cumulative_reward_points) + points

    elif event_type == "adjustment":
        commission = Decimal("0.00")
        reward_base = Decimal("0.00")
        if points_delta is None:
            raise ValueError("points_delta is required for adjustment")
        points = _to_decimal(points_delta)
        account.cumulative_reward_points = _to_decimal(account.cumulative_reward_points) + points

    ledger = PartnerRewardLedger(
        partner_account_id=account.id,
        order_ref=order_ref,
        product_id=product_id,
        click_id=click_id,
        event_type=event_type,
        applied_share_rate=event_share_rate,
        commission_amount=commission,
        reward_base_amount=reward_base,
        points_delta=points,
        note=note,
    )
    db.add(ledger)
    db.flush()

    lifetime_settled_commission = _apply_tier_upgrade(db, account)

    db.commit()
    db.refresh(ledger)
    db.refresh(account)

    return {
        "ledger_id": ledger.id,
        "partner_account_id": account.id,
        "event_type": ledger.event_type,
        "commission_amount": float(ledger.commission_amount or 0),
        "reward_base_amount": float(ledger.reward_base_amount or 0),
        "points_delta": float(ledger.points_delta or 0),
        "applied_share_rate": float(ledger.applied_share_rate or 0),
        "tier_code": account.tier_code,
        "share_rate": float(account.share_rate),
        "net_settled_commission": float(account.cumulative_settled_commission or 0),
        "lifetime_settled_commission": float(lifetime_settled_commission),
        "net_reward_points": float(account.cumulative_reward_points or 0),
    }


def get_partner_reward_overview(
    db: Session,
    *,
    wechat_openid: str,
    recent_limit: int | None = None,
) -> dict:
    rules = load_partner_reward_rules()
    program_rules = load_partner_program_rules()
    account = _get_partner_account_by_openid(db, wechat_openid)

    rows = (
        db.query(PartnerRewardLedger)
        .filter(PartnerRewardLedger.partner_account_id == account.id)
        .order_by(PartnerRewardLedger.id.desc())
        .all()
    )

    estimated_reward = Decimal("0.00")
    settled_reward = Decimal("0.00")
    reversed_reward = Decimal("0.00")
    redeemed_points = Decimal("0.00")
    available_points = Decimal("0.00")

    for row in rows:
        reward_base = _to_decimal(row.reward_base_amount)
        points = _to_decimal(row.points_delta)

        if row.event_type == "estimated":
            estimated_reward += reward_base
        elif row.event_type == "settled":
            settled_reward += reward_base
        elif row.event_type == "reversed":
            reversed_reward += abs(reward_base)
        elif row.event_type == "redeem":
            redeemed_points += abs(points)

        available_points += points

    lifetime_settled_commission = _get_lifetime_settled_commission(db, account.id)
    tier_payload = program_rules["tiers"][account.tier_code]

    limit = recent_limit or int(rules["default_recent_limit"])
    recent_rows = []
    for row in rows[:limit]:
        recent_rows.append(
            {
                "ledger_id": row.id,
                "event_type": row.event_type,
                "order_ref": row.order_ref,
                "product_id": row.product_id,
                "click_id": row.click_id,
                "applied_share_rate": float(row.applied_share_rate or 0),
                "commission_amount": float(_to_decimal(row.commission_amount)),
                "reward_base_amount": float(_to_decimal(row.reward_base_amount)),
                "points_delta": float(_to_decimal(row.points_delta)),
                "note": row.note,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )

    return {
        "partner_account_id": account.id,
        "tier_code": account.tier_code,
        "tier_name": tier_payload["name"],
        "share_rate": float(account.share_rate),
        "entry_rules": program_rules["entry_rules"],
        "point_use_plan": rules["point_use_plan"],
        "net_settled_commission": float(_to_decimal(account.cumulative_settled_commission)),
        "lifetime_settled_commission": float(lifetime_settled_commission),
        "available_points": float(available_points),
        "estimated_reward": float(estimated_reward),
        "settled_reward": float(settled_reward),
        "reversed_reward": float(reversed_reward),
        "redeemed_points": float(redeemed_points),
        "recent": recent_rows,
    }
