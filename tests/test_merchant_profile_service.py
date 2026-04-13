from app.services.merchant_profile_service import build_category_price_medians, build_merchant_snapshot


def test_build_category_price_medians():
    goods = [
        {"categoryInfo": {"cid3Name": "牙膏"}, "priceInfo": {"price": 100}},
        {"categoryInfo": {"cid3Name": "牙膏"}, "priceInfo": {"price": 120}},
        {"categoryInfo": {"cid3Name": "牙膏"}, "priceInfo": {"price": 140}},
        {"categoryInfo": {"cid3Name": "水果罐头"}, "priceInfo": {"price": 60}},
    ]
    medians = build_category_price_medians(goods)
    assert medians["牙膏"] == 120.0
    assert medians["水果罐头"] == 60.0


def test_build_merchant_snapshot_risky_shop():
    item = {
        "owner": "p",
        "priceInfo": {"price": 160},
        "shopInfo": {
            "shopId": 123,
            "shopName": "测试高风险店",
            "shopLabel": "0",
            "userEvaluateScore": "8.5",
            "afterServiceScore": "8.4",
            "logisticsLvyueScore": "8.3",
            "scoreRankRate": "60",
        },
    }
    snapshot = build_merchant_snapshot(item, category_median_price=100)
    assert snapshot["shop_id"] == "123"
    assert snapshot["recommendable"] is False
    assert "poor_reputation" in snapshot["risk_flags"]
    assert "poor_after_sales" in snapshot["risk_flags"]
    assert "price_too_high" in snapshot["risk_flags"]


def test_build_merchant_snapshot_self_operated_with_missing_scores():
    item = {
        "owner": "g",
        "priceInfo": {"price": 100},
        "shopInfo": {
            "shopId": 456,
            "shopName": "京东自营店",
            "shopLabel": "1",
        },
    }
    snapshot = build_merchant_snapshot(item, category_median_price=100)
    assert snapshot["merchant_health_score"] >= 75
    assert snapshot["recommendable"] is True
