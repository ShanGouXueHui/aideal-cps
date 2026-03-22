from sqlalchemy.orm import Session

from app.models.user import User


def get_or_create_test_user(db: Session, nickname: str = "test_user"):
    user = db.query(User).filter(User.subunionid == "u_1001").first()
    if user:
        return user

    user = User(
        wechat_openid="wx_openid_test_1001",
        wechat_unionid="wx_unionid_test_1001",
        nickname=nickname,
        subunionid="u_1001",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
