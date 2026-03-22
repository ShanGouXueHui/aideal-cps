from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.user_service import get_or_create_test_user

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/test-init")
def init_test_user(db: Session = Depends(get_db)):
    user = get_or_create_test_user(db)
    return {
        "id": user.id,
        "nickname": user.nickname,
        "subunionid": user.subunionid,
        "wechat_openid": user.wechat_openid,
        "wechat_unionid": user.wechat_unionid,
    }
