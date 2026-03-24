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
请把下面这段电商推荐理由，改写成更像真人推荐、带一点“占便宜”和“从众心理”的表达，但不要夸张或虚假：

原文：
{raw_text}

要求：
- 更口语化
- 更有说服力
- 控制在1句话
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
        result = resp.json()
        return result["output"]["choices"][0]["message"]["content"].strip()
    except Exception:
        return raw_text
