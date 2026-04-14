from app.services import message_router as router


def test_text_share_product_keyword_routes_to_share_entry(monkeypatch):
    monkeypatch.setattr(router, "build_text_response", lambda to_user, from_user, text: text)
    monkeypatch.setattr(
        router,
        "get_partner_share_product_request_reply",
        lambda db, openid, content: "动态分享商品摘要" if content == "分享商品 牙膏" else None,
    )

    msg = {
        "FromUserName": "user_openid",
        "ToUserName": "gh_aideal",
        "MsgType": "text",
        "Content": "分享商品 牙膏",
    }

    result = router.route(msg)
    assert result == "动态分享商品摘要"
