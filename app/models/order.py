from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.core.db import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    jd_order_id = Column(String(64), unique=True, nullable=False, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)

    subunionid = Column(String(64), nullable=True, index=True)
    site_id = Column(String(64), nullable=True, index=True)
    position_id = Column(String(64), nullable=True, index=True)

    sku_id = Column(String(64), nullable=True, index=True)
    sku_name = Column(String(255), nullable=True)

    order_amount = Column(Float, default=0.0)
    actual_cos_price = Column(Float, default=0.0)
    estimate_cos_price = Column(Float, default=0.0)

    order_status = Column(String(50), default="pending")
    order_time = Column(DateTime(timezone=True), nullable=True)
    finish_time = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
