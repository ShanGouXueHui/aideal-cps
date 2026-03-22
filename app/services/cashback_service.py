from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.models.order import Order
from app.models.cashback_record import CashbackRecord


def init_cashback_from_order(db: Session, order_id: int):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("Order not found")

    existing = db.query(CashbackRecord).filter(CashbackRecord.order_id == order.id).first()
    if existing:
        return existing

    # 一期简单规则：按实际佣金的 50% 作为预估返现金额
    expected_cashback_amount = round((order.actual_cos_price or 0.0) * 0.5, 2)

    record = CashbackRecord(
        user_id=order.user_id,
        order_id=order.id,
        expected_cashback_amount=expected_cashback_amount,
        actual_cashback_amount=0.0,
        status="pending",
        remark="initialized from order",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_cashback_records(db: Session, page: int = 1, page_size: int = 20):
    query = db.query(CashbackRecord)

    total = query.count()
    items = (
        query.order_by(desc(CashbackRecord.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "items": items,
    }


def get_overview_report(db: Session):
    total_orders = db.query(func.count(Order.id)).scalar() or 0
    total_order_amount = db.query(func.coalesce(func.sum(Order.order_amount), 0)).scalar() or 0
    total_actual_commission = db.query(func.coalesce(func.sum(Order.actual_cos_price), 0)).scalar() or 0
    total_estimated_commission = db.query(func.coalesce(func.sum(Order.estimate_cos_price), 0)).scalar() or 0

    total_cashback_expected = db.query(
        func.coalesce(func.sum(CashbackRecord.expected_cashback_amount), 0)
    ).scalar() or 0

    total_cashback_actual = db.query(
        func.coalesce(func.sum(CashbackRecord.actual_cashback_amount), 0)
    ).scalar() or 0

    net_income = round(float(total_actual_commission) - float(total_cashback_actual), 2)

    return {
        "total_orders": int(total_orders),
        "total_order_amount": float(total_order_amount),
        "total_actual_commission": float(total_actual_commission),
        "total_estimated_commission": float(total_estimated_commission),
        "total_cashback_expected": float(total_cashback_expected),
        "total_cashback_actual": float(total_cashback_actual),
        "net_income": net_income,
    }
