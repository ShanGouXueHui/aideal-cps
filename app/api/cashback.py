from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.cashback import CashbackListResponse, OverviewResponse
from app.services.cashback_service import (
    init_cashback_from_order,
    list_cashback_records,
    get_overview_report,
)

router = APIRouter(tags=["cashback"])


@router.post("/cashback/init-from-order")
def create_cashback_from_order(order_id: int, db: Session = Depends(get_db)):
    try:
        record = init_cashback_from_order(db=db, order_id=order_id)
        return {
            "id": record.id,
            "user_id": record.user_id,
            "order_id": record.order_id,
            "expected_cashback_amount": record.expected_cashback_amount,
            "actual_cashback_amount": record.actual_cashback_amount,
            "status": record.status,
            "remark": record.remark,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/cashback", response_model=CashbackListResponse)
def get_cashback_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return list_cashback_records(db=db, page=page, page_size=page_size)


@router.get("/reports/overview", response_model=OverviewResponse)
def get_reports_overview(db: Session = Depends(get_db)):
    return get_overview_report(db=db)
