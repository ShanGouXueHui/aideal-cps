from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.formatters import money, money_wan
from app.services.cashback_service import get_overview_report, list_cashback_records
from app.services.order_service import list_orders
from app.services.product_service import get_products

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")


@router.get("/overview")
def admin_overview(request: Request, db: Session = Depends(get_db)):
    overview = get_overview_report(db)

    return templates.TemplateResponse(
        "admin_overview.html",
        {
            "request": request,
            "overview": overview,
            "overview_wan": {
                "total_order_amount": money_wan(overview["total_order_amount"]),
                "total_actual_commission": money_wan(overview["total_actual_commission"]),
                "total_estimated_commission": money_wan(overview["total_estimated_commission"]),
                "total_cashback_expected": money_wan(overview["total_cashback_expected"]),
                "total_cashback_actual": money_wan(overview["total_cashback_actual"]),
                "net_income": money_wan(overview["net_income"]),
            },
        },
    )


@router.get("/products")
def admin_products(request: Request, db: Session = Depends(get_db)):
    result = get_products(db=db, page=1, page_size=100)
    return templates.TemplateResponse(
        "admin_products.html",
        {
            "request": request,
            "total": result["total"],
            "items": result["items"],
            "money": money,
        },
    )


@router.get("/orders")
def admin_orders(request: Request, db: Session = Depends(get_db)):
    result = list_orders(db=db, page=1, page_size=100)
    return templates.TemplateResponse(
        "admin_orders.html",
        {
            "request": request,
            "total": result["total"],
            "items": result["items"],
            "money": money,
        },
    )


@router.get("/cashback")
def admin_cashback(request: Request, db: Session = Depends(get_db)):
    result = list_cashback_records(db=db, page=1, page_size=100)
    return templates.TemplateResponse(
        "admin_cashback.html",
        {
            "request": request,
            "total": result["total"],
            "items": result["items"],
            "money": money,
        },
    )
