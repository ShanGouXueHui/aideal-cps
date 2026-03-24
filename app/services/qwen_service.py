import requests

from app.core.config import settings


def rewrite_reason(raw_text: str) -> str:
    if not settings.QWEN_API_KEY:
        return raw_text

    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

    headers = {
        "Authorization": f"Bearer {settings.QWEN_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
请把下面这段电商推荐理由，改写成更自然、更像真人推荐的一句话。

原文：
{raw_text}

要求：
1. 只能基于原文润色，禁止新增任何价格、销量、优惠金额、佣金、库存、时效信息
2. 禁止虚假宣传、禁止绝对化表达、禁止夸大
3. 禁止使用“最后机会、马上涨价、全网最低、闭眼入”等高风险措辞
4. 保持口语化，但要克制、可信
5. 控制在1句话，尽量20~30字
"""

    data = {
        "model": settings.QWEN_MODEL,
        "input": {
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        return result["output"]["choices"][0]["message"]["content"].strip()
    except Exception:
        return raw_text
