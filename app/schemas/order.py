from typing import Optional, List
from pydantic import BaseModel


class OrderItem(BaseModel):
    id: int
    jd_order_id: str
    user_id: Optional[int] = None
    product_id: Optional[int] = None
    subunionid: Optional[str] = None
    site_id: Optional[str] = None
    position_id: Optional[str] = None
    sku_id: Optional[str] = None
    sku_name: Optional[str] = None
    order_amount: float
    actual_cos_price: float
    estimate_cos_price: float
    order_status: str

    model_config = {
        "from_attributes": True
    }


class OrderListResponse(BaseModel):
    total: int
    items: List[OrderItem]
