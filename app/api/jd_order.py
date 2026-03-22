from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.jd_order_service import sync_mock_orders

router = APIRouter(prefix="/jd", tags=["jd"])


@router.post("/orders/sync")
def jd_orders_sync(db: Session = Depends(get_db)):
    return sync_mock_orders(db)
