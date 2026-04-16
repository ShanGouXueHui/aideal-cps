from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.sql import func

from app.core.db import Base


class WechatRecommendExposure(Base):
    __tablename__ = "wechat_recommend_exposures"

    id = Column(Integer, primary_key=True, index=True)
    openid_hash = Column(String(64), nullable=False, index=True)
    scene = Column(String(64), nullable=False, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    __table_args__ = (
        Index(
            "ix_wechat_recommend_exposure_lookup",
            "openid_hash",
            "scene",
            "created_at",
        ),
    )
