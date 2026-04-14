from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.core.db import Base


class PartnerShareClick(Base):
    __tablename__ = "partner_share_clicks"

    id = Column(Integer, primary_key=True, index=True)
    partner_account_id = Column(Integer, ForeignKey("partner_accounts.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("partner_share_assets.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    request_source = Column(String(64), nullable=True)
    client_ip = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    referer = Column(String(1000), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
