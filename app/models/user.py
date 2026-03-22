from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    wechat_openid = Column(String(64), unique=True, nullable=True)
    wechat_unionid = Column(String(64), unique=True, nullable=True)
    nickname = Column(String(128), nullable=True)

    subunionid = Column(String(64), unique=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
