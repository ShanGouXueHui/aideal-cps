from sqlalchemy.orm import Session

from app.models.product import Product


def sync_mock_products(db: Session):
    mock_products = [
        {
            "jd_sku_id": "1000001",
            "title": "Apple iPhone 15 128GB 黑色",
            "description": "高销量热门手机，适合日常使用和送礼。",
            "image_url": "https://example.com/iphone15.jpg",
            "product_url": "https://item.jd.com/1000001.html",
            "category_name": "手机数码",
            "shop_name": "京东自营",
            "price": 4999.00,
            "coupon_price": 4699.00,
            "commission_rate": 2.5,
            "estimated_commission": 124.98,
            "sales_volume": 20000,
            "coupon_info": "满5000减300",
            "ai_reason": "品牌认知强，适合追求稳定体验的用户。",
            "ai_tags": "高销量,旗舰机,送礼推荐",
            "status": "active",
        },
        {
            "jd_sku_id": "1000002",
            "title": "小米空气炸锅 6L 大容量",
            "description": "家庭厨房高频使用小家电。",
            "image_url": "https://example.com/airfryer.jpg",
            "product_url": "https://item.jd.com/1000002.html",
            "category_name": "家用电器",
            "shop_name": "小米京东自营旗舰店",
            "price": 299.00,
            "coupon_price": 249.00,
            "commission_rate": 8.0,
            "estimated_commission": 19.92,
            "sales_volume": 50000,
            "coupon_info": "满299减50",
            "ai_reason": "客单价适中、转化率高，适合家庭用户和厨房场景推广。",
            "ai_tags": "高佣金,厨房好物,家庭必备",
            "status": "active",
        },
        {
            "jd_sku_id": "1000003",
            "title": "南极人 保暖内衣套装 男款秋冬加绒",
            "description": "秋冬应季商品，价格敏感型用户转化较好。",
            "image_url": "https://example.com/warmwear.jpg",
            "product_url": "https://item.jd.com/1000003.html",
            "category_name": "服饰内衣",
            "shop_name": "南极人官方旗舰店",
            "price": 89.90,
            "coupon_price": 79.90,
            "commission_rate": 12.0,
            "estimated_commission": 9.59,
            "sales_volume": 80000,
            "coupon_info": "2件9折",
            "ai_reason": "价格低、需求广、季节性强，适合做爆品引流。",
            "ai_tags": "高销量,应季爆品,低价引流",
            "status": "active",
        },
    ]

    inserted = 0
    updated = 0

    for item in mock_products:
        existing = db.query(Product).filter(Product.jd_sku_id == item["jd_sku_id"]).first()

        if existing:
            for key, value in item.items():
                setattr(existing, key, value)
            updated += 1
        else:
            db.add(Product(**item))
            inserted += 1

    db.commit()

    return {
        "message": "mock products synced successfully",
        "inserted": inserted,
        "updated": updated,
        "total": len(mock_products),
    }
