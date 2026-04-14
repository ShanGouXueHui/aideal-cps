from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.partner_account import PartnerAccount
from app.models.user import User
from app.services.partner_program_config_service import load_partner_program_rules


def _generate_subunionid(db: Session) -> str:
    while True:
        value = "wx_" + secrets.token_hex(8)
        exists = db.query(User).filter(User.subunionid == value).first()
        if not exists:
            return value


def _generate_partner_code(db: Session) -> str:
    while True:
        value = "p" + secrets.token_hex(4)
        exists = db.query(PartnerAccount).filter(PartnerAccount.partner_code == value).first()
        if not exists:
            return value


def get_or_create_user_by_openid(db: Session, wechat_openid: str) -> User:
    user = db.query(User).filter(User.wechat_openid == wechat_openid).first()
    if user:
        return user

    user = User(
        wechat_openid=wechat_openid,
        nickname=None,
        subunionid=_generate_subunionid(db),
        wechat_unionid=None,
    )
    db.add(user)
    db.flush()
    return user


def _tier_payload(tier_code: str) -> dict:
    rules = load_partner_program_rules()
    tiers = rules["tiers"]
    if tier_code not in tiers:
        raise ValueError(f"Unknown tier_code: {tier_code}")
    return tiers[tier_code]


def enroll_partner_by_openid(db: Session, wechat_openid: str) -> dict:
    rules = load_partner_program_rules()
    user = get_or_create_user_by_openid(db, wechat_openid)
    account = db.query(PartnerAccount).filter(PartnerAccount.user_id == user.id).first()
    if not account:
        tier_code = rules["default_tier"]
        tier = _tier_payload(tier_code)
        account = PartnerAccount(
            user_id=user.id,
            partner_code=_generate_partner_code(db),
            status=rules["default_status"],
            tier_code=tier_code,
            share_rate=float(tier["share_rate"]),
            cumulative_paid_gmv=Decimal("0.00"),
            cumulative_settled_commission=Decimal("0.00"),
            cumulative_reward_points=Decimal("0.00"),
            activated_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc),
        )
        db.add(account)
        db.commit()
        db.refresh(account)
    else:
        account.last_active_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(account)

    tier = _tier_payload(account.tier_code)
    return {
        "user_id": user.id,
        "wechat_openid": user.wechat_openid,
        "subunionid": user.subunionid,
        "partner_account_id": account.id,
        "partner_code": account.partner_code,
        "status": account.status,
        "tier_code": account.tier_code,
        "tier_name": tier["name"],
        "share_rate": float(account.share_rate),
    }


def get_partner_account_by_code(db: Session, partner_code: str) -> PartnerAccount | None:
    return db.query(PartnerAccount).filter(PartnerAccount.partner_code == partner_code).first()
