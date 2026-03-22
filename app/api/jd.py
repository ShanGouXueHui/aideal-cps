from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.jd_service import sync_mock_products

router = APIRouter(prefix="/jd", tags=["jd"])


@router.post("/products/sync")
def jd_products_sync(db: Session = Depends(get_db)):
    return sync_mock_products(db)
