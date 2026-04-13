from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.core.db import Base


class ClickLog(Base):
    __tablename__ = "click_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    subunionid = Column(String(64), nullable=False, index=True)

    wechat_openid = Column(String(64), nullable=True, index=True)
    request_source = Column(String(50), nullable=True)
    scene = Column(String(50), nullable=True, index=True)
    slot = Column(Integer, nullable=True, index=True)
    trace_id = Column(String(64), nullable=True, index=True)

    promotion_url = Column(String(1000), nullable=True)
    final_url = Column(String(1000), nullable=True)
    material_url = Column(String(1000), nullable=True)
    short_url = Column(String(1000), nullable=True)

    client_ip = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    referer = Column(String(1000), nullable=True)

    click_time = Column(DateTime(timezone=True), server_default=func.now())
