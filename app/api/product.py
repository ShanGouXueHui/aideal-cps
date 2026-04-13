from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.product import ProductListResponse, ProductDetailResponse
from app.services.product_service import get_products, get_product_by_id

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    category_name: Optional[str] = None,
    elite_id: Optional[int] = None,
    elite_name: Optional[str] = None,
    shop_name: Optional[str] = None,
    min_commission_rate: Optional[float] = Query(None, ge=0),
    min_merchant_health_score: Optional[float] = Query(None, ge=0),
    has_short_url: Optional[bool] = None,
    merchant_recommendable_only: Optional[bool] = Query(True),
    order_by: str = Query("sales_volume"),
    sort: str = Query("desc"),
    db: Session = Depends(get_db),
):
    return get_products(
        db=db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        category_name=category_name,
        elite_id=elite_id,
        elite_name=elite_name,
        shop_name=shop_name,
        min_commission_rate=min_commission_rate,
        min_merchant_health_score=min_merchant_health_score,
        has_short_url=has_short_url,
        merchant_recommendable_only=merchant_recommendable_only,
        order_by=order_by,
        sort=sort,
    )


@router.get("/{product_id}", response_model=ProductDetailResponse)
def product_detail(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
