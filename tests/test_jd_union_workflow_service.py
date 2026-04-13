from app.services.jd_union_workflow_service import JDUnionWorkflowService


class DummyClient:
    def jingfen_query(self, *, elite_id, page_index=1, page_size=20):
        return {
            "jd_union_open_goods_jingfen_query_responce": {
                "queryResult": {
                    "code": 200,
                    "data": [
                        {
                            "skuName": "测试商品A",
                            "brandName": "测试品牌",
                            "materialUrl": "https://jingfen.jd.com/detail/abc.html",
                            "priceInfo": {"price": 99, "lowestCouponPrice": 79},
                            "commissionInfo": {"commission": 12.5, "commissionShare": 20},
                            "resourceInfo": {"eliteId": elite_id, "eliteName": "高佣榜"},
                        }
                    ],
                }
            }
        }

    def promotion_bysubunionid_get(self, *, material_id, chain_type=2, scene_id=1):
        return {
            "jd_union_open_promotion_bysubunionid_get_responce": {
                "getResult": {
                    "code": 200,
                    "data": {"shortURL": "https://u.jd.com/test"},
                    "message": "success",
                }
            }
        }


def test_query_goods_with_links():
    service = JDUnionWorkflowService(client=DummyClient())
    rows = service.query_goods_with_links(elite_id=129, limit=1)
    assert len(rows) == 1
    assert rows[0]["skuName"] == "测试商品A"
    assert rows[0]["shortURL"] == "https://u.jd.com/test"
    assert rows[0]["commission"] == 12.5
