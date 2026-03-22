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
    db: Session = Depends(get_db),
):
    return get_products(
        db=db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        category_name=category_name,
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
