from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.core.db import Base


class ClickLog(Base):
    __tablename__ = "click_logs"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    subunionid = Column(String(64), nullable=False, index=True)
    promotion_url = Column(String(1000), nullable=True)

    click_time = Column(DateTime(timezone=True), server_default=func.now())
