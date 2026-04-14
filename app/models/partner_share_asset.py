from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.core.db import Base


class PartnerShareAsset(Base):
    __tablename__ = "partner_share_assets"

    id = Column(Integer, primary_key=True, index=True)
    partner_account_id = Column(Integer, ForeignKey("partner_accounts.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    asset_token = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, index=True)
    rank_tags = Column(String(255), nullable=True)
    short_url = Column(String(1000), nullable=True)
    long_url = Column(String(1000), nullable=True)
    buy_url = Column(String(1000), nullable=True)
    share_url = Column(String(1000), nullable=True)
    buy_copy = Column(Text, nullable=True)
    share_copy = Column(Text, nullable=True)
    buy_qr_svg_path = Column(String(1000), nullable=True)
    share_qr_svg_path = Column(String(1000), nullable=True)
    poster_svg_path = Column(String(1000), nullable=True)
    j_command_short = Column(String(255), nullable=True)
    j_command_long = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
