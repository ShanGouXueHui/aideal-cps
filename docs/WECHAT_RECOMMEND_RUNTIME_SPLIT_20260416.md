# WeChat 推荐稳定运行时模块切换说明（2026-04-16）

## 背景
原 `wechat_recommend_h5_service.py` 经多轮快速 patch 后，已经出现大量重复定义：
- `_select_today_batch`
- `_find_entry_product`
- `get_today_recommend_text_reply`
- `get_find_product_entry_text_reply`
- `render_product_h5`
- `has_today_recommend_products`
- `has_find_entry_product`

线上虽然可以通过“最后定义覆盖前面定义”的方式运行，但这会导致：
1. 修改不可预测
2. 新 patch 容易破坏旧功能
3. 故障难定位

## 本轮处理
新增：
- `app/services/wechat_recommend_runtime_service.py`

并把活跃入口切换到新模块：
- `message_router.py`
- `app/api/wechat_recommend_h5.py`

## 当前好处
1. 推荐文本生成、H5 渲染、更多同类产品入口不再依赖旧大文件中的重复定义
2. 后续修改有明确落点
3. 线上主链路已经形成更稳定的边界：
   - callback
   - recommend text
   - h5 detail
   - more-like-this
   - promotion redirect

## 后续建议
1. 将 runtime 模块继续拆成：
   - selection
   - text
   - page
   - link
2. 旧 `wechat_recommend_h5_service.py` 做最终下线和归档
3. 再做“更多同类产品”公众号内直回 3 条
