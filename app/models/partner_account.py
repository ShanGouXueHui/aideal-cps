from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.sql import func

from app.core.db import Base


class PartnerAccount(Base):
    __tablename__ = "partner_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    partner_code = Column(String(32), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, index=True)
    tier_code = Column(String(32), nullable=False, index=True)
    share_rate = Column(Float, nullable=False)
    cumulative_paid_gmv = Column(Numeric(12, 2), nullable=True, server_default="0")
    cumulative_settled_commission = Column(Numeric(12, 2), nullable=True, server_default="0")
    cumulative_reward_points = Column(Numeric(12, 2), nullable=True, server_default="0")
    activated_at = Column(DateTime(timezone=True), nullable=True)
    last_active_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
