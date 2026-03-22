from fastapi import FastAPI

from app.api.product import router as product_router
from app.api.jd import router as jd_router
from app.api.user import router as user_router
from app.api.promotion import router as promotion_router
from app.api.order import router as order_router

app = FastAPI(title="AIdeal CPS", version="0.1.0")

app.include_router(product_router)
app.include_router(jd_router)
app.include_router(user_router)
app.include_router(promotion_router)
app.include_router(order_router)


@app.get("/")
def root():
    return {
        "message": "AIdeal CPS backend is running",
        "status": "ok"
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
