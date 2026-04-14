from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from app.core.db import Base


class PartnerPointRedemption(Base):
    __tablename__ = "partner_point_redemptions"

    id = Column(Integer, primary_key=True, index=True)
    partner_account_id = Column(Integer, ForeignKey("partner_accounts.id"), nullable=False, index=True)

    item_code = Column(String(64), nullable=False, index=True)
    item_name = Column(String(255), nullable=False)
    scene_code = Column(String(64), nullable=False, index=True)

    cash_price_rmb = Column(Numeric(12, 2), nullable=False, server_default="0")
    points_used = Column(Numeric(12, 2), nullable=False, server_default="0")
    cash_due_rmb = Column(Numeric(12, 2), nullable=False, server_default="0")

    status = Column(String(32), nullable=False, index=True)
    fulfill_mode = Column(String(32), nullable=True)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    fulfilled_at = Column(DateTime(timezone=True), nullable=True)
