import json

from app.core.jd_union_config import parse_pid_for_site_position
from app.services.jd_union_client import JDUnionClient, extract_jingfen_items


def test_parse_pid_for_site_position():
    site_id, position_id = parse_pid_for_site_position("2037986512_4103601247_3104059194")
    assert site_id == "4103601247"
    assert position_id == "3104059194"


def test_build_request_params_contains_required_fields():
    client = JDUnionClient(
        app_key="test_app_key",
        app_secret="test_app_secret",
        pid="2037986512_4103601247_3104059194",
        base_url="https://api.jd.com/routerjson",
    )

    params = client._build_request_params(
        "jd.union.open.goods.jingfen.query",
        {"goodsReq": {"eliteId": 129, "pageIndex": 1, "pageSize": 20}},
        timestamp="2026-04-01 20:08:59",
    )

    assert params["method"] == "jd.union.open.goods.jingfen.query"
    assert params["app_key"] == "test_app_key"
    assert params["v"] == "1.0"
    assert params["format"] == "json"
    assert params["sign_method"] == "md5"
    assert "360buy_param_json" in params
    assert params["sign"]
    assert json.loads(params["360buy_param_json"])["goodsReq"]["eliteId"] == 129


def test_jingfen_query_calls_expected_method(monkeypatch):
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jd_union_open_goods_jingfen_query_responce": {
                    "queryResult": {
                        "code": 200,
                        "data": [{"materialUrl": "https://example.com/item"}],
                    }
                }
            }

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("app.services.jd_union_client.requests.get", fake_get)

    client = JDUnionClient(
        app_key="test_app_key",
        app_secret="test_app_secret",
        pid="2037986512_4103601247_3104059194",
        base_url="https://api.jd.com/routerjson",
        timeout_seconds=9,
    )

    response = client.jingfen_query(elite_id=129, page_size=3)

    assert captured["url"] == "https://api.jd.com/routerjson"
    assert captured["params"]["method"] == "jd.union.open.goods.jingfen.query"
    assert captured["params"]["sign_method"] == "md5"
    assert captured["timeout"] == 9
    assert extract_jingfen_items(response)[0]["materialUrl"] == "https://example.com/item"
