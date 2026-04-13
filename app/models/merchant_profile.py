from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.sql import func

from app.core.db import Base


class MerchantProfile(Base):
    __tablename__ = "merchant_profiles"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(String(64), unique=True, index=True, nullable=False)
    shop_name = Column(String(255), nullable=True)
    shop_label = Column(String(50), nullable=True)
    owner = Column(String(20), nullable=True)

    user_evaluate_score = Column(Float, nullable=True)
    after_service_score = Column(Float, nullable=True)
    logistics_lvyue_score = Column(Float, nullable=True)
    score_rank_rate = Column(Float, nullable=True)

    merchant_health_score = Column(Float, nullable=True, index=True)
    risk_flags = Column(String(255), nullable=True)
    recommendable = Column(Boolean, default=True, index=True)
    source = Column(String(20), default="jd")
    last_sync_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
