from typing import List, Optional
from pydantic import BaseModel


class CashbackItem(BaseModel):
    id: int
    user_id: int
    order_id: int
    expected_cashback_amount: float
    actual_cashback_amount: float
    status: str
    remark: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


class CashbackListResponse(BaseModel):
    total: int
    items: List[CashbackItem]


class OverviewResponse(BaseModel):
    total_orders: int
    total_order_amount: float
    total_actual_commission: float
    total_estimated_commission: float
    total_cashback_expected: float
    total_cashback_actual: float
    net_income: float


class CashbackUpdateRequest(BaseModel):
    actual_cashback_amount: float
    status: str
    remark: Optional[str] = None
