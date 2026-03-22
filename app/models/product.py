from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.sql import func

from app.core.db import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    jd_sku_id = Column(String(64), unique=True, index=True, nullable=False)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    image_url = Column(String(500), nullable=True)
    product_url = Column(String(500), nullable=True)

    category_name = Column(String(100), nullable=True)
    shop_name = Column(String(255), nullable=True)

    price = Column(Float, default=0.0)
    coupon_price = Column(Float, default=0.0)

    commission_rate = Column(Float, default=0.0)
    estimated_commission = Column(Float, default=0.0)

    sales_volume = Column(Integer, default=0)

    coupon_info = Column(String(255), nullable=True)

    ai_reason = Column(Text, nullable=True)
    ai_tags = Column(String(255), nullable=True)

    status = Column(String(50), default="active")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
