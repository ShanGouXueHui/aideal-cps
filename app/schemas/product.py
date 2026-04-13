from typing import Optional, List
from pydantic import BaseModel


class ProductItem(BaseModel):
    id: int
    jd_sku_id: str
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    material_url: Optional[str] = None
    short_url: Optional[str] = None
    category_name: Optional[str] = None
    shop_name: Optional[str] = None
    shop_id: Optional[str] = None
    price: float
    coupon_price: float
    commission_rate: float
    estimated_commission: float
    sales_volume: int
    coupon_info: Optional[str] = None
    ai_reason: Optional[str] = None
    ai_tags: Optional[str] = None
    elite_id: Optional[int] = None
    elite_name: Optional[str] = None
    owner: Optional[str] = None
    merchant_health_score: Optional[float] = None
    merchant_risk_flags: Optional[str] = None
    merchant_recommendable: Optional[bool] = None
    status: str

    model_config = {
        "from_attributes": True
    }


class ProductListResponse(BaseModel):
    total: int
    items: List[ProductItem]


class ProductDetailResponse(ProductItem):
    pass
