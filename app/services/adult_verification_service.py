from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.adult_verification_config_service import load_adult_verification_rules


def _build_subunionid(wechat_openid: str) -> str:
    digest = hashlib.md5(wechat_openid.encode("utf-8")).hexdigest()[:16]
    return f"adult_{digest}"


def _get_or_create_user(db: Session, wechat_openid: str) -> User:
    user = db.query(User).filter(User.wechat_openid == wechat_openid).first()
    if user:
        return user

    user = User(
        wechat_openid=wechat_openid,
        subunionid=_build_subunionid(wechat_openid),
    )
    db.add(user)
    db.commit()
    return db.query(User).filter(User.wechat_openid == wechat_openid).first()


def get_adult_verification_status(db: Session, wechat_openid: str) -> dict:
    rules = load_adult_verification_rules()
    user = db.query(User).filter(User.wechat_openid == wechat_openid).first()
    if not user:
        return {
            "wechat_openid": wechat_openid,
            "adult_verified": False,
            "adult_verified_at": None,
            "verification_source": None,
            "notice": rules["min_age_notice"],
        }

    return {
        "wechat_openid": wechat_openid,
        "adult_verified": bool(user.adult_verified),
        "adult_verified_at": user.adult_verified_at.isoformat() if user.adult_verified_at else None,
        "verification_source": user.verification_source,
        "notice": rules["min_age_notice"],
    }


def mark_user_adult_verified(
    db: Session,
    *,
    wechat_openid: str,
    verification_source: str | None = None,
) -> dict:
    rules = load_adult_verification_rules()
    user = _get_or_create_user(db, wechat_openid)

    if not user:
        raise ValueError("User not found after creation")

    user.adult_verified = True
    user.adult_verified_at = datetime.now(timezone.utc)
    user.verification_source = verification_source or rules["verification_source_default"]

    db.commit()

    user = db.query(User).filter(User.wechat_openid == wechat_openid).first()
    if not user:
        raise ValueError("User missing after update")

    return {
        "wechat_openid": wechat_openid,
        "adult_verified": True,
        "adult_verified_at": user.adult_verified_at.isoformat() if user.adult_verified_at else None,
        "verification_source": user.verification_source,
        "message": rules["success_message"],
    }


def build_adult_verification_url(wechat_openid: str) -> str:
    rules = load_adult_verification_rules()
    base_url = rules["public_base_url"].rstrip("/")
    return f"{base_url}/h5/adult-verify?wechat_openid={wechat_openid}"
