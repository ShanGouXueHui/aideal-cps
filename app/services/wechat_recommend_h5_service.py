from __future__ import annotations

"""
兼容层：
- 当前推荐链路的唯一真实实现位于 app.services.wechat_recommend_runtime_service
- 本文件只保留旧导入路径兼容，禁止继续在这里堆业务逻辑
- 若后续要修改推荐逻辑，请只改 runtime_service
"""

from app.services.wechat_recommend_runtime_service import (
    get_find_product_entry_text_reply,
    get_product_by_id,
    get_today_recommend_text_reply,
    has_find_entry_product,
    has_today_recommend_products,
    render_product_h5,
)

__all__ = [
    "get_today_recommend_text_reply",
    "get_find_product_entry_text_reply",
    "has_today_recommend_products",
    "has_find_entry_product",
    "get_product_by_id",
    "render_product_h5",
]
