from app.api.wechat import router as wechat_router
from app.api.wechat_recommend_h5 import router as wechat_recommend_h5_router
from app.api.product import router as product_router
from app.api.jd import router as jd_router
from app.api.promotion import router as promotion_router
from app.api.partner import router as partner_router
from app.api.user_profile import router as user_profile_router
from app.api.partner_materials import router as partner_materials_router
from fastapi import FastAPI

app = FastAPI(title="AIdeal CPS API")

app.include_router(wechat_router)
app.include_router(wechat_recommend_h5_router)
app.include_router(product_router)
app.include_router(jd_router)
app.include_router(promotion_router)
app.include_router(partner_router)
app.include_router(user_profile_router)
app.include_router(partner_materials_router)


@app.get("/")
def root():
    return {"message": "AIdeal CPS is running"}
