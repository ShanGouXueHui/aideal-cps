from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Numeric
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

    material_url = Column(String(500), nullable=True)
    short_url = Column(String(500), nullable=True)

    category_name = Column(String(100), nullable=True)
    shop_name = Column(String(255), nullable=True)
    shop_id = Column(String(64), nullable=True, index=True)

    price = Column(Numeric(12, 2), default=0.00)
    coupon_price = Column(Numeric(12, 2), default=0.00)

    commission_rate = Column(Float, default=0.0)
    estimated_commission = Column(Numeric(12, 2), default=0.00)
    sales_volume = Column(Integer, default=0)

    coupon_info = Column(String(255), nullable=True)

    ai_reason = Column(Text, nullable=True)
    ai_tags = Column(String(255), nullable=True)

    elite_id = Column(Integer, nullable=True, index=True)
    elite_name = Column(String(100), nullable=True)
    owner = Column(String(20), nullable=True)

    status = Column(String(50), default="active")

    last_sync_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
