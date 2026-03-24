import secrets
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.user import User


def generate_subunionid() -> str:
    return "wx_" + secrets.token_hex(8)


def get_or_create_user_by_openid(openid: str, nickname: str | None = None) -> User:
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.wechat_openid == openid).first()
        if user:
            if nickname and not user.nickname:
                user.nickname = nickname
                db.commit()
                db.refresh(user)
            return user

        while True:
            subunionid = generate_subunionid()
            exists = db.query(User).filter(User.subunionid == subunionid).first()
            if not exists:
                break

        user = User(
            wechat_openid=openid,
            nickname=nickname,
            subunionid=subunionid,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def get_or_create_test_user(db: Session) -> User:
    user = db.query(User).filter(User.wechat_openid == "test_openid_001").first()
    if user:
        return user

    while True:
        subunionid = generate_subunionid()
        exists = db.query(User).filter(User.subunionid == subunionid).first()
        if not exists:
            break

    user = User(
        wechat_openid="test_openid_001",
        nickname="test_user",
        subunionid=subunionid,
        wechat_unionid=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
