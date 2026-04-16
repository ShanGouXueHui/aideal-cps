from app.main import app
from app.api.wechat_recommend_h5 import router as wechat_recommend_h5_router
app.include_router(wechat_recommend_h5_router)
