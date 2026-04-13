from __future__ import annotations

import re
from typing import Any

SHOPPING_HINTS = {
    "买", "购买", "想买", "推荐", "便宜", "划算", "优惠", "值得买", "囤", "到手价",
    "卫生纸", "纸巾", "抽纸", "卷纸", "卫生巾", "苏菲", "护垫", "洗衣液", "湿巾",
    "牙膏", "牙刷", "洗发水", "沐浴露", "零食", "罐头", "母婴", "宝宝", "自营",
}

QUALITY_HINTS = {"质量", "靠谱", "耐用", "口碑", "好评", "稳", "正品", "官方", "自营"}
LOW_PRICE_HINTS = {"便宜", "划算", "省钱", "低价", "优惠", "折扣", "券后", "便宜点"}
SALES_HINTS = {"销量", "下单多", "买的人多", "热销", "爆款"}

ATTRIBUTE_TOKENS = [
    "夜用", "日用", "超薄", "超长", "棉柔", "敏感肌", "宝宝", "家庭装",
    "囤货装", "自营", "官方旗舰店", "大包装", "抽取式", "卷纸",
]

COMMODITY_TERMS = [
    "卫生纸", "纸巾", "抽纸", "卷纸", "卫生巾", "护垫", "洗衣液", "湿巾",
    "牙膏", "牙刷", "洗发水", "沐浴露", "零食", "罐头", "奶粉", "尿不湿",
]

STOPWORDS = [
    "我想买", "我想要", "帮我找", "帮我买", "给我找", "给我推荐", "推荐一下",
    "我想", "想买", "购买", "买一包", "买一卷", "买一瓶", "买", "一下", "要求",
    "价格", "京东官网", "京东", "官网", "比", "更", "要", "的", "一个", "一包", "一卷",
]


def normalize_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"[，。！？、,.!?\n\r\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_shopping_intent(text: str) -> bool:
    text = normalize_text(text)
    if not text:
        return False
    return any(word in text for word in SHOPPING_HINTS)


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        value = value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def parse_product_intent(text: str) -> dict[str, Any]:
    original = normalize_text(text)
    shopping_intent = is_shopping_intent(original)

    wants_low_price = any(word in original for word in LOW_PRICE_HINTS)
    wants_quality = any(word in original for word in QUALITY_HINTS)
    wants_sales = any(word in original for word in SALES_HINTS)
    wants_self_operated = ("自营" in original) or ("官方" in original)

    commodity = None
    for term in COMMODITY_TERMS:
        if term in original:
            commodity = term
            break

    attribute_tokens = [token for token in ATTRIBUTE_TOKENS if token in original]

    cleaned = original
    for word in STOPWORDS:
        cleaned = cleaned.replace(word, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    search_tokens: list[str] = []
    if cleaned:
        search_tokens.append(cleaned)

    if commodity:
        search_tokens.append(commodity)

    for token in attribute_tokens:
        search_tokens.append(token)

    if commodity and cleaned and commodity in cleaned:
        prefix = cleaned.split(commodity)[0].strip()
        if 1 < len(prefix) <= 8:
            search_tokens.append(prefix)

    # 若没有明确商品词，但有购物意图，则保留原文作为兜底搜索
    if not search_tokens and original:
        search_tokens.append(original)

    search_tokens = [token for token in search_tokens if len(token) >= 2]
    search_tokens = _dedupe_keep_order(search_tokens)

    return {
        "original_text": original,
        "shopping_intent": shopping_intent,
        "commodity": commodity,
        "attribute_tokens": attribute_tokens,
        "search_tokens": search_tokens,
        "wants_low_price": wants_low_price,
        "wants_quality": wants_quality,
        "wants_sales": wants_sales,
        "wants_self_operated": wants_self_operated,
    }
