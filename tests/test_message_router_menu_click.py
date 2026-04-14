from app.services import message_router as router


def test_click_find_product(monkeypatch):
    monkeypatch.setattr(router, "build_text_response", lambda to_user, from_user, text: text)

    msg = {
        "FromUserName": "user_openid",
        "ToUserName": "gh_aideal",
        "MsgType": "event",
        "Event": "CLICK",
        "EventKey": "找商品",
    }

    result = router.route(msg)
    assert "直接告诉我你想买什么" in result


def test_click_partner_center_uses_dynamic_reply(monkeypatch):
    monkeypatch.setattr(router, "build_text_response", lambda to_user, from_user, text: text)
    monkeypatch.setattr(router, "get_partner_center_entry_reply", lambda db, openid: "动态合伙人中心摘要")

    msg = {
        "FromUserName": "user_openid",
        "ToUserName": "gh_aideal",
        "MsgType": "event",
        "Event": "CLICK",
        "EventKey": "合伙人中心",
    }

    result = router.route(msg)
    assert result == "动态合伙人中心摘要"


def test_text_today_recommend_uses_dynamic_reply(monkeypatch):
    monkeypatch.setattr(router, "build_text_response", lambda to_user, from_user, text: text)
    monkeypatch.setattr(router, "get_today_recommend_reply", lambda db, openid: "动态今日推荐结果")

    msg = {
        "FromUserName": "user_openid",
        "ToUserName": "gh_aideal",
        "MsgType": "text",
        "Content": "今日推荐",
    }

    result = router.route(msg)
    assert result == "动态今日推荐结果"
