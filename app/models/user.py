from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Text
from sqlalchemy.sql import func

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    wechat_openid = Column(String(64), unique=True, nullable=True)
    wechat_unionid = Column(String(64), unique=True, nullable=True)
    nickname = Column(String(128), nullable=True)
    subunionid = Column(String(64), unique=True, nullable=False)

    first_subscribe_at = Column(DateTime(timezone=True), nullable=True)
    last_interaction_at = Column(DateTime(timezone=True), index=True, nullable=True)
    interaction_count = Column(Integer, default=0)

    price_sensitive_score = Column(Float, default=0.0)
    quality_sensitive_score = Column(Float, default=0.0)
    sales_sensitive_score = Column(Float, default=0.0)
    self_operated_sensitive_score = Column(Float, default=0.0)

    preferred_categories = Column(Text, nullable=True)
    last_query_text = Column(Text, nullable=True)

    morning_push_enabled = Column(Boolean, default=True, index=True)
    morning_push_hour = Column(Integer, default=8, index=True)
    last_push_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
