from app.services.wechat_menu_service import get_menu_entry_reply


def test_find_product_menu_reply():
    reply = get_menu_entry_reply("找商品")
    assert reply is not None
    assert "直接告诉我你想买什么" in reply


def test_today_recommend_menu_reply():
    reply = get_menu_entry_reply("今日推荐")
    assert reply is not None
    assert "今日热销" in reply


def test_partner_center_menu_reply():
    reply = get_menu_entry_reply("合伙人中心")
    assert reply is not None
    assert "合伙人中心" in reply
