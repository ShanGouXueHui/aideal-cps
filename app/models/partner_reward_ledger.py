from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from app.core.db import Base


class PartnerRewardLedger(Base):
    __tablename__ = "partner_reward_ledgers"

    id = Column(Integer, primary_key=True, index=True)
    partner_account_id = Column(Integer, ForeignKey("partner_accounts.id"), nullable=False, index=True)
    order_ref = Column(String(128), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    click_id = Column(Integer, nullable=True, index=True)

    event_type = Column(String(32), nullable=False, index=True)
    applied_share_rate = Column(Float, nullable=True)

    commission_amount = Column(Numeric(12, 2), nullable=False, server_default="0")
    reward_base_amount = Column(Numeric(12, 2), nullable=False, server_default="0")
    points_delta = Column(Numeric(12, 2), nullable=False, server_default="0")

    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
