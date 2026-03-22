from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.promotion_service import create_promotion_link

router = APIRouter(prefix="/promotion", tags=["promotion"])


@router.post("/link")
def generate_promotion_link(
    user_id: int,
    product_id: int,
    db: Session = Depends(get_db),
):
    try:
        return create_promotion_link(db=db, user_id=user_id, product_id=product_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
