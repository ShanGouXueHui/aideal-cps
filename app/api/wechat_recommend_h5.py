from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.wechat_recommend_runtime_service import get_product_by_id, render_product_h5

router = APIRouter()


@router.get("/api/h5/recommend/more-like-this")
async def recommend_more_like_this_page(
    product_id: int,
    scene: str = Query(default=""),
    slot: str = Query(default=""),
    wechat_openid: str = Query(default=""),
):
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
            .order_by(Product.comment_count.desc(), Product.sales_volume.desc(), Product.id.desc())
            .limit(12)
            .all()
        )

        cards = []
        for idx, x in enumerate(rows[:3], 1):
            purchase_price = getattr(x, "purchase_price", None)
            basis_price = getattr(x, "basis_price", None)
            price_text = "以下单页实时信息为准"
            try:
                if purchase_price is not None and basis_price is not None:
                    delta = float(basis_price) - float(purchase_price)
                    price_text = f"优惠价￥{float(purchase_price):.2f}｜京东官网价￥{float(basis_price):.2f}｜立省￥{delta:.2f}"
            except Exception:
                pass

            detail_link = f"/api/h5/recommend/{int(x.id)}?scene=more_like_this&slot={idx}&wechat_openid={wechat_openid}"
            buy_link = (
                f"/api/promotion/redirect?"
                f"wechat_openid={wechat_openid}&product_id={int(x.id)}&scene=more_like_this&slot={idx}"
            )

            cards.append(
                f"""
                <div style="background:#fff;border-radius:16px;padding:16px;margin:12px 0;box-shadow:0 4px 16px rgba(15,23,42,.06);">
                  <div style="font-size:16px;font-weight:700;line-height:1.6;color:#111827;">{x.title}</div>
                  <div style="margin-top:10px;color:#475569;line-height:1.8;">💰 到手参考：{price_text}</div>
                  <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
                    <a href="{detail_link}" style="display:inline-block;padding:10px 14px;border-radius:10px;background:#eef2ff;color:#3730a3;text-decoration:none;">图文详情</a>
                    <a href="{buy_link}" style="display:inline-block;padding:10px 14px;border-radius:10px;background:#dcfce7;color:#166534;text-decoration:none;">下单链接</a>
                  </div>
                </div>
                """
            )

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
            {''.join(cards) if cards else '<div style="margin-top:16px;">当前还没有更多同类商品。</div>'}
          </div>
        </body>
        </html>
        """
        return HTMLResponse(html)
    finally:
        db.close()


@router.get("/api/h5/recommend/{product_id}")
async def recommend_detail_page(
    product_id: int,
    scene: str = Query(default=""),
    slot: str = Query(default=""),
    wechat_openid: str = Query(default=""),
):
    db = SessionLocal()
    try:
        product = get_product_by_id(db, int(product_id))
        if not product:
            return HTMLResponse("<h3>商品不存在</h3>", status_code=404)
        return HTMLResponse(render_product_h5(product, scene=scene, slot=slot, wechat_openid=wechat_openid))
    finally:
        db.close()
