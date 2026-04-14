from app.services import wechat_menu_sync_service as svc


def test_load_wechat_menu_payload():
    payload = svc.load_wechat_menu_payload()
    assert "button" in payload
    assert len(payload["button"]) == 3
    assert payload["button"][0]["name"] == "找商品"


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
