from decimal import Decimal

from app.services.qwen_service import rewrite_reason


def _safe_decimal(value):
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def calculate_product_score(product) -> Decimal:
    """
    score =
      sales_volume * 0.5 +
      commission_rate * 0.3 +
      discount_rate * 0.2
    """
    sales_volume = _safe_decimal(getattr(product, "sales_volume", 0) or 0)
    commission_rate = _safe_decimal(getattr(product, "commission_rate", 0) or 0)
    price = _safe_decimal(getattr(product, "price", 0))
    coupon_price = _safe_decimal(getattr(product, "coupon_price", 0))

    if price > 0:
        discount_rate = (price - coupon_price) / price
        if discount_rate < 0:
            discount_rate = Decimal("0")
    else:
        discount_rate = Decimal("0")

    return (
        sales_volume * Decimal("0.5") +
        commission_rate * Decimal("0.3") +
        discount_rate * Decimal("0.2")
    )


def select_top_product(products):
    if not products:
        return None
    return max(products, key=calculate_product_score)


def generate_reason(product) -> str:
    sales_volume = int(getattr(product, "sales_volume", 0) or 0)
    price = _safe_decimal(getattr(product, "price", 0))
    coupon_price = _safe_decimal(getattr(product, "coupon_price", 0))
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
    elif sales_volume > 0:
        raw = f"已有{sales_text}人购买，热度不错"
    else:
        raw = "这款商品当前价格比较合适，适合直接看看"

    # 再用 Qwen 润色
    return rewrite_reason(raw)
