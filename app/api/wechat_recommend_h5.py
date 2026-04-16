from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.core.db import SessionLocal
from app.services.wechat_recommend_h5_service import get_product_by_id, render_product_h5

router = APIRouter()


@router.get("/api/h5/recommend/{product_id}", response_class=HTMLResponse)
async def recommend_detail_page(product_id: int, scene: str = Query(default=""), slot: str = Query(default="")):
    db = SessionLocal()
    try:
        product = get_product_by_id(db, product_id)
        if not product:
            return PlainTextResponse("商品不存在或已下架", status_code=404)
        return HTMLResponse(render_product_h5(product, scene=scene, slot=slot))
    finally:
        db.close()


@router.get("/api/h5/recommend/more-like-this")
async def recommend_more_like_this_page(product_id: int, scene: str = Query(default=""), slot: str = Query(default="")):
    db = SessionLocal()
    try:
        base_product = get_product_by_id(db, int(product_id))
        if not base_product:
            return HTMLResponse("<h3>商品不存在</h3>", status_code=404)

        rows = (
            db.query(Product)
            .filter(Product.status == "active")
            .filter(Product.allow_proactive_push == True)
            .filter(Product.short_url.isnot(None), Product.short_url != "")
            .filter(Product.id != int(product_id))
            .filter(Product.category_name == base_product.category_name)
            .limit(12)
            .all()
        )

        items = []
        for x in rows[:3]:
            items.append(f"""
            <div style="background:#fff;border-radius:16px;padding:16px;margin:12px 0;box-shadow:0 4px 16px rgba(15,23,42,.06);">
              <div style="font-size:16px;font-weight:700;line-height:1.6;color:#111827;">{x.title}</div>
              <div style="margin-top:10px;color:#475569;line-height:1.8;">到手参考：{getattr(x, 'purchase_price', '')}</div>
              <div style="margin-top:12px;">
                <a href="/api/h5/recommend/{int(x.id)}?scene=more_like_this&slot=1" style="display:inline-block;padding:10px 14px;border-radius:10px;background:#eef2ff;color:#3730a3;text-decoration:none;margin-right:8px;">图文详情</a>
                <a href="/api/promotion/redirect?product_id={int(x.id)}&scene=more_like_this&slot=1" style="display:inline-block;padding:10px 14px;border-radius:10px;background:#dcfce7;color:#166534;text-decoration:none;">下单链接</a>
              </div>
            </div>
            """)

        html = f"""
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
          <title>更多同类产品</title>
          <style>
            body{{margin:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f172a;}}
            .wrap{{max-width:760px;margin:0 auto;padding:20px 16px 40px;}}
            .title{{font-size:22px;font-weight:800;line-height:1.5;}}
            .sub{{margin-top:8px;color:#64748b;line-height:1.7;}}
          </style>
        </head>
        <body>
          <div class="wrap">
            <div class="title">更多同类产品</div>
            <div class="sub">基于当前商品分类，补充 3 个可继续对比的同类商品。</div>
            {''.join(items) if items else '<div style="margin-top:16px;">当前还没有更多同类商品。</div>'}
          </div>
        </body>
        </html>
        """
        return HTMLResponse(html)
    finally:
        db.close()
