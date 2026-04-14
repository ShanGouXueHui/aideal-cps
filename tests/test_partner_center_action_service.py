from app.services import partner_center_action_service as svc


def test_points_reply_from_center_payload(monkeypatch):
    monkeypatch.setattr(
        svc,
        "_load_partner_center_payload",
        lambda db, wechat_openid: {
            "reward_overview": {
                "tier_name": "正式合伙人",
                "share_rate": 0.5,
                "available_points": 320,
                "net_settled_commission": 1200,
                "settled_reward": 500,
                "redeemed_points": 180,
                "point_use_plan": {
                    "supported_scenes": [
                        {"scene_name": "合伙人开通/续费抵扣"},
                        {"scene_name": "精选选品服务包抵扣"},
                    ]
                },
            }
        },
    )
    reply = svc.get_partner_points_reply(None, "wx_test")
    assert "可用积分：320.00" in reply
    assert "累计已结算佣金：¥1200.00" in reply


def test_share_products_reply_from_center_payload(monkeypatch):
    monkeypatch.setattr(
        svc,
        "_load_partner_center_payload",
        lambda db, wechat_openid: {
            "recent_shareable_products": [
                {
                    "title": "维达卷纸超值装",
                    "shop_name": "维达旗舰店",
                    "coupon_price": 39.9,
                    "commission_rate": 12,
                },
                {
                    "title": "清风卷纸家庭装",
                    "shop_name": "清风旗舰店",
                    "coupon_price": 49.9,
                    "commission_rate": 10,
                },
            ]
        },
    )
    reply = svc.get_partner_share_products_reply(None, "wx_test")
    assert "维达卷纸超值装" in reply
    assert "佣金率参考：12.00%" in reply


def test_route_partner_center_action_dispatches_assets(monkeypatch):
    monkeypatch.setattr(svc, "get_partner_assets_reply", lambda db, wechat_openid: "动态素材摘要")
    reply = svc.route_partner_center_action(None, "wx_test", "素材")
    assert reply == "动态素材摘要"
