from app.services import wechat_menu_sync_service as svc


def test_load_wechat_menu_payload():
    payload = svc.load_wechat_menu_payload()
    assert "button" in payload
    assert len(payload["button"]) == 3
    assert payload["button"][0]["name"] == "找商品"


def test_create_wechat_menu_uses_utf8_body(monkeypatch):
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"errcode": 0, "errmsg": "ok"}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(svc.requests, "post", fake_post)

    payload = {
        "button": [
            {"type": "click", "name": "找商品", "key": "找商品"}
        ]
    }
    result = svc.create_wechat_menu("mock_token", payload)

    assert result["errcode"] == 0
    assert isinstance(captured["data"], bytes)
    assert b"\\u627e\\u5546\\u54c1" not in captured["data"]
    assert "charset=utf-8" in captured["headers"]["Content-Type"]


def test_sync_wechat_menu_flow(monkeypatch):
    monkeypatch.setattr(svc, "get_wechat_access_token", lambda: "mock_token")
    monkeypatch.setattr(
        svc,
        "create_wechat_menu",
        lambda access_token, payload: {"errcode": 0, "errmsg": "ok"},
    )
    monkeypatch.setattr(
        svc,
        "get_wechat_menu",
        lambda access_token: {"is_menu_open": 1, "selfmenu_info": {"button": [{"name": "找商品"}]}},
    )

    result = svc.sync_wechat_menu()
    assert result["create_result"]["errcode"] == 0
    assert result["current_menu"]["is_menu_open"] == 1
