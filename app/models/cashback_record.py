from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Numeric
from sqlalchemy.sql import func

from app.core.db import Base


class CashbackRecord(Base):
    __tablename__ = "cashback_records"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)

    expected_cashback_amount = Column(Numeric(12, 2), default=0.00)
    actual_cashback_amount = Column(Numeric(12, 2), default=0.00)

    status = Column(String(50), default="pending")
    remark = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
