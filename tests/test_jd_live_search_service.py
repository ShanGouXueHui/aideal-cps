from app.services.jd_live_search_service import search_live_jd_products


class FakeJDClient:
    def goods_query(self, **kwargs):
        return {
            "jd_union_open_goods_query_responce": {
                "queryResult": {
                    "code": 200,
                    "data": [
                        {
                            "skuId": 1001,
                            "skuName": "苏菲夜用卫生巾超熟睡组合",
                            "materialUrl": "https://item.m.jd.com/product/1001.html",
                            "priceInfo": {"price": 59.9, "lowestCouponPrice": 39.9},
                            "commissionInfo": {"commissionShare": 20, "commission": 8},
                            "categoryInfo": {"cid3Name": "卫生巾"},
                            "shopInfo": {"shopName": "苏菲官方旗舰店", "shopId": 11},
                            "inOrderCount30DaysSku": 888,
                            "forbidTypes": [0],
                        },
                        {
                            "skuId": 1002,
                            "skuName": "女性防狼喷雾",
                            "materialUrl": "https://item.m.jd.com/product/1002.html",
                            "priceInfo": {"price": 19.9, "lowestCouponPrice": 19.9},
                            "commissionInfo": {"commissionShare": 30, "commission": 6},
                            "categoryInfo": {"cid3Name": "防身用品"},
                            "shopInfo": {"shopName": "风险店铺", "shopId": 22},
                            "inOrderCount30DaysSku": 99,
                            "forbidTypes": [0],
                        },
                    ],
                }
            }
        }

    def promotion_bysubunionid_get(self, **kwargs):
        material_id = kwargs["material_id"]
        return {
            "jd_union_open_promotion_bysubunionid_get_responce": {
                "getResult": {
                    "code": 200,
                    "data": {"shortURL": f"https://u.jd.com/mock?to={material_id}"},
                    "message": "success",
                }
            }
        }


def test_search_live_jd_products_filters_hard_block():
    rows = search_live_jd_products(
        query_text="卫生巾",
        jd_client=FakeJDClient(),
        adult_verified=False,
        limit=5,
    )
    assert len(rows) == 1
    assert rows[0]["title"] == "苏菲夜用卫生巾超熟睡组合"
    assert rows[0]["compliance_level"] == "normal"
    assert rows[0]["short_url"].startswith("https://u.jd.com/mock")
