from __future__ import annotations

from app.services.wechat_menu_config_service import get_menu_entry_map


MENU_KEY_ALIASES = {
    "找商品": "find_product",
    "今日推荐": "today_recommend",
    "合伙人中心": "partner_center",
    "热销": "today_recommend",
    "高佣": "today_recommend",
    "活动": "today_recommend"
}


def resolve_menu_entry_key(user_text: str | None) -> str | None:
    text = (user_text or "").strip()
    if not text:
        return None
    return MENU_KEY_ALIASES.get(text)


def get_menu_entry_reply(user_text: str | None) -> str | None:
    key = resolve_menu_entry_key(user_text)
    if not key:
        return None
    entry = get_menu_entry_map().get(key)
    if not entry:
        return None
    return entry.get("reply_text")
