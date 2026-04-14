from app.services import message_router as router


def test_text_points_routes_partner_action(monkeypatch):
    monkeypatch.setattr(router, "build_text_response", lambda to_user, from_user, text: text)
    monkeypatch.setattr(router, "route_partner_center_action", lambda db, openid, content: "动态积分摘要" if content == "积分" else None)

    msg = {
        "FromUserName": "user_openid",
        "ToUserName": "gh_aideal",
        "MsgType": "text",
        "Content": "积分",
    }

    result = router.route(msg)
    assert result == "动态积分摘要"


def test_click_assets_routes_partner_action(monkeypatch):
    monkeypatch.setattr(router, "build_text_response", lambda to_user, from_user, text: text)
    monkeypatch.setattr(router, "route_partner_center_action", lambda db, openid, content: "动态素材摘要" if content == "素材" else None)

    msg = {
        "FromUserName": "user_openid",
        "ToUserName": "gh_aideal",
        "MsgType": "event",
        "Event": "CLICK",
        "EventKey": "素材",
    }

    result = router.route(msg)
    assert result == "动态素材摘要"
