from decimal import Decimal
from app.services.qwen_service import rewrite_reason


def _safe_decimal(value):
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def generate_reason(product) -> str:
    sales_volume = product.sales_volume or 0
    price = _safe_decimal(product.price)
    coupon_price = _safe_decimal(product.coupon_price)

    discount = price - coupon_price
    if discount < 0:
        discount = Decimal("0")

    discount_text = f"{discount:.2f}".rstrip("0").rstrip(".") if discount else "0"
    sales_text = str(sales_volume)

    # 先生成“事实版”
    if sales_volume >= 10000 and discount > 0:
        raw = f"已有{sales_text}人购买，当前券后立减{discount_text}元，到手价更划算"
    elif discount > 0:
        raw = f"当前券后比标价便宜{discount_text}元，价格更实惠"
    else:
        raw = f"已有{sales_text}人购买，热度不错"

    # 再用 Qwen 润色
    return rewrite_reason(raw)
