import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.user import User
from app.services.user_crypto_service import encrypt_text, hash_identity, normalize_identity


def generate_subunionid() -> str:
    return "wx_" + secrets.token_hex(8)


def _unique_subunionid(db: Session) -> str:
    while True:
        subunionid = generate_subunionid()
        exists = db.query(User).filter(User.subunionid == subunionid).first()
        if not exists:
            return subunionid


def get_or_create_user_by_openid_db(db: Session, openid: str, nickname: str | None = None) -> User:
    openid_norm = normalize_identity(openid)
    if not openid_norm:
        raise ValueError("openid is required")

    openid_hash = hash_identity(openid_norm)
    user = db.query(User).filter(User.wechat_openid_hash == openid_hash).first()
    if user:
        if nickname and not getattr(user, "nickname_ciphertext", None):
            user.nickname = None
            user.nickname_ciphertext = encrypt_text(nickname)
            db.flush()
        return user

    user = User(
        wechat_openid=None,
        wechat_openid_hash=openid_hash,
        wechat_openid_ciphertext=encrypt_text(openid_norm),
        nickname=None,
        nickname_ciphertext=encrypt_text(nickname),
        subunionid=_unique_subunionid(db),
        first_subscribe_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def get_or_create_user_by_openid(openid: str, nickname: str | None = None) -> User:
    db: Session = SessionLocal()
    try:
        user = get_or_create_user_by_openid_db(db, openid, nickname=nickname)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def get_or_create_test_user(db: Session) -> User:
    return get_or_create_user_by_openid_db(db, "test_openid_001", nickname="test_user")
