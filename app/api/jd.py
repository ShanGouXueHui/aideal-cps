from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db

router = APIRouter(prefix="/jd", tags=["jd"])


@router.post("/products/sync")
def jd_products_sync(db: Session = Depends(get_db)):
    return {
        "message": "jd product sync is temporarily disabled",
        "status": "placeholder"
    }
