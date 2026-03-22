from typing import Optional, List
from pydantic import BaseModel


class ProductItem(BaseModel):
    id: int
    jd_sku_id: str
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    category_name: Optional[str] = None
    shop_name: Optional[str] = None
    price: float
    coupon_price: float
    commission_rate: float
    estimated_commission: float
    sales_volume: int
    coupon_info: Optional[str] = None
    ai_reason: Optional[str] = None
    ai_tags: Optional[str] = None
    status: str

    model_config = {
        "from_attributes": True
    }


class ProductListResponse(BaseModel):
    total: int
    items: List[ProductItem]


class ProductDetailResponse(ProductItem):
    pass
