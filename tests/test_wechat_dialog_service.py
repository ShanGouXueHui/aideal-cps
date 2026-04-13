from types import SimpleNamespace

from app.services.wechat_dialog_service import select_three_products


def _product(id, title, sales, health, commission, owner="p"):
    return SimpleNamespace(
        id=id,
        title=title,
        sales_volume=sales,
        merchant_health_score=health,
        commission_rate=commission,
        coupon_price=10,
        price=20,
        shop_name="测试店铺",
        owner=owner,
    )


def test_select_three_products():
    products = [
        _product(1, "苏菲夜用卫生巾", 100, 80, 10),
        _product(2, "销量最高卫生巾", 1000, 70, 5),
        _product(3, "更稳妥卫生巾", 50, 95, 8, owner="g"),
    ]
    intent = {
        "search_tokens": ["苏菲", "卫生巾", "夜用"],
        "wants_low_price": True,
        "wants_quality": False,
        "wants_sales": False,
        "wants_self_operated": False,
    }
    result = select_three_products(products, intent)
    assert len(result) == 3
    assert result[0][1].id == 1
    assert result[1][1].id == 2
    assert result[2][1].id == 3
