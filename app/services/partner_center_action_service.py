from __future__ import annotations

from typing import Any


ACTION_ALIASES = {
    "积分": "points",
    "我的积分": "points",
    "积分明细": "points",
    "素材": "assets",
    "素材包": "assets",
    "推广素材": "assets",
    "分享商品": "share_products",
    "可分享商品": "share_products",
    "续费": "renewal",
    "合伙人续费": "renewal",
}


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def resolve_partner_action_key(user_text: str | None) -> str | None:
    text = (user_text or "").strip()
    if not text:
        return None
    return ACTION_ALIASES.get(text)


def _call_service_func(func, db, wechat_openid: str):
    errors = []
    for kwargs in (
        {"db": db, "wechat_openid": wechat_openid},
        {"session": db, "wechat_openid": wechat_openid},
    ):
        try:
            return func(**kwargs)
        except TypeError as exc:
            errors.append(exc)

    for args in (
        (db, wechat_openid),
        (db,),
    ):
        try:
            return func(*args)
        except TypeError as exc:
            errors.append(exc)

    if errors:
        raise errors[-1]
    return None


def _load_partner_center_payload(db, wechat_openid: str) -> dict | None:
    try:
        import app.services.partner_center_service as mod
    except Exception:
        return None

    for func_name in (
        "get_partner_center_payload",
        "build_partner_center_payload",
        "get_partner_center",
        "build_partner_center",
        "get_partner_center_summary",
    ):
        func = getattr(mod, func_name, None)
        if not callable(func):
            continue
        try:
            result = _call_service_func(func, db, wechat_openid)
            if isinstance(result, dict):
                return result
        except Exception:
            continue
    return None


def _load_reward_overview(db, wechat_openid: str) -> dict | None:
    try:
        from app.services.partner_reward_service import get_partner_reward_overview
    except Exception:
        return None

    try:
        result = get_partner_reward_overview(db, wechat_openid=wechat_openid)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    return None


def _supported_scene_names(point_use_plan: dict | None) -> list[str]:
    names: list[str] = []
    for item in (point_use_plan or {}).get("supported_scenes", []) or []:
        scene_name = item.get("scene_name")
        if scene_name:
            names.append(scene_name)
    return names


def get_partner_points_reply(db, wechat_openid: str) -> str:
    payload = _load_partner_center_payload(db, wechat_openid) or {}
    reward_overview = payload.get("reward_overview") or _load_reward_overview(db, wechat_openid)

    if not reward_overview:
        return (
            "你当前还没有可展示的积分数据。\n"
            "等有分享成交或积分入账后，这里会展示可用积分、已结算佣金和可抵扣场景。"
        )

    available_points = _safe_float(reward_overview.get("available_points"))
    net_commission = _safe_float(reward_overview.get("net_settled_commission"))
    redeemed_points = _safe_float(reward_overview.get("redeemed_points"))
    settled_reward = _safe_float(reward_overview.get("settled_reward"))
    share_rate = _safe_float(reward_overview.get("share_rate"))
    tier_name = reward_overview.get("tier_name") or reward_overview.get("tier_code") or "正式合伙人"

    scene_names = _supported_scene_names(reward_overview.get("point_use_plan"))
    scene_text = "、".join(scene_names[:3]) if scene_names else "开通/续费、精选服务、素材包"

    return (
        "你的积分与收益摘要：\n\n"
        f"当前等级：{tier_name}\n"
        f"当前分成比例：{share_rate:.2f}\n"
        f"可用积分：{available_points:.2f}\n"
        f"累计已结算佣金：¥{net_commission:.2f}\n"
        f"累计已入账奖励积分：{settled_reward:.2f}\n"
        f"累计已消耗积分：{redeemed_points:.2f}\n\n"
        f"当前积分可优先用于：{scene_text}"
    )


def get_partner_assets_reply(db, wechat_openid: str) -> str:
    payload = _load_partner_center_payload(db, wechat_openid) or {}
    recent_assets = payload.get("recent_assets") or []
    recent_products = payload.get("recent_shareable_products") or []

    if not recent_assets and not recent_products:
        return (
            "你当前还没有可展示的素材记录。\n"
            "等你生成过分享素材后，这里会展示最近素材和可继续分享的商品。"
        )

    lines = ["你的素材与可分享商品摘要：", ""]

    if recent_assets:
        lines.append(f"最近已生成素材：{len(recent_assets)} 个")
        for idx, item in enumerate(recent_assets[:3], start=1):
            title = item.get("title") or f"素材#{idx}"
            lines.append(f"{idx}. {title}")
        lines.append("")

    if recent_products:
        lines.append("当前可继续分享的商品：")
        for idx, item in enumerate(recent_products[:3], start=1):
            title = item.get("title") or f"商品#{idx}"
            shop_name = item.get("shop_name") or "未知店铺"
            price = item.get("coupon_price") or item.get("price")
            try:
                price_text = f"¥{float(price):.2f}" if price is not None else "以页面为准"
            except Exception:
                price_text = "以页面为准"
            lines.append(f"{idx}. {title} | {shop_name} | {price_text}")

    lines.extend(["", "你也可以直接回复：分享商品，我给你继续挑适合分发的商品。"])
    return "\n".join(lines)


def get_partner_share_products_reply(db, wechat_openid: str) -> str:
    payload = _load_partner_center_payload(db, wechat_openid) or {}
    products = payload.get("recent_shareable_products") or []

    if not products:
        return (
            "当前还没有现成的可分享商品摘要。\n"
            "你可以直接回复商品名，比如“牙膏”或“洗衣液”，我再按当前商品池给你挑适合分享的。"
        )

    lines = ["当前适合继续分享的商品里，先给你看 3 个：", ""]
    for idx, item in enumerate(products[:3], start=1):
        title = item.get("title") or f"商品#{idx}"
        shop_name = item.get("shop_name") or "未知店铺"
        price = item.get("coupon_price") or item.get("price")
        commission_rate = _safe_float(item.get("commission_rate"))
        try:
            price_text = f"¥{float(price):.2f}" if price is not None else "以页面为准"
        except Exception:
            price_text = "以页面为准"

        lines.append(f"{idx}. {title}")
        lines.append(f"店铺：{shop_name}")
        lines.append(f"到手参考：{price_text}")
        if commission_rate > 0:
            lines.append(f"佣金率参考：{commission_rate:.2f}%")
        lines.append("")

    lines.append("你后面可以继续回复具体商品名，我再给你生成对应分享素材。")
    return "\n".join(lines).strip()


def get_partner_renewal_reply(db, wechat_openid: str) -> str:
    payload = _load_partner_center_payload(db, wechat_openid) or {}
    reward_overview = payload.get("reward_overview") or {}
    redemption_options = payload.get("redemption_options") or {}

    available_points = _safe_float(reward_overview.get("available_points"))
    items = redemption_options.get("items") or []

    renewal_item = None
    for item in items:
        if item.get("item_code") == "partner_renewal_fee":
            renewal_item = item
            break

    if not renewal_item:
        return (
            "合伙人续费入口已经预留。\n"
            "当前规则是：可用积分优先抵扣，不足部分再补现金。"
        )

    cash_price = _safe_float(renewal_item.get("cash_price_rmb"))
    max_points_ratio = _safe_float(renewal_item.get("max_points_ratio") or 1.0)
    max_points = min(available_points, cash_price * max_points_ratio)
    cash_due = max(cash_price - max_points, 0)

    return (
        "合伙人续费说明：\n\n"
        f"续费项目：{renewal_item.get('item_name') or '合伙人续费'}\n"
        f"标准价格：¥{cash_price:.2f}\n"
        f"当前可用积分：{available_points:.2f}\n"
        f"本次最多可抵扣：{max_points:.2f} 积分\n"
        f"预计还需现金：¥{cash_due:.2f}\n\n"
        "下一步我可以继续把续费动作接成真实入口。"
    )


def route_partner_center_action(db, wechat_openid: str, content: str | None) -> str | None:
    action_key = resolve_partner_action_key(content)
    if not action_key:
        return None

    if action_key == "points":
        return get_partner_points_reply(db, wechat_openid)
    if action_key == "assets":
        return get_partner_assets_reply(db, wechat_openid)
    if action_key == "share_products":
        return get_partner_share_products_reply(db, wechat_openid)
    if action_key == "renewal":
        return get_partner_renewal_reply(db, wechat_openid)
    return None
