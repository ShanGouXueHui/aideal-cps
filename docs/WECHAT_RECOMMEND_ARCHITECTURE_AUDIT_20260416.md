# WeChat 推荐链路架构审计（2026-04-16）

## 1. 当前问题本质
这次故障不是单点 bug，而是多轮快速 patch 后形成的“边界漂移”：

1. API 层与 Service 层调用契约不稳定  
   - API 直接调用 service
   - 但 service 真实签名要求 `db`
   - 导致 redirect 路由持续 500

2. 推荐 H5 服务文件被多轮 override  
   - 同名函数被多次追加 / 覆盖
   - 局部修复之间互相影响
   - 典型表现：
     - `_detail_url`
     - `_more_like_this_url`
     - `get_today_recommend_text_reply`
     - `render_product_h5`

3. 线上问题表象
   - 服务号返回 temporarily unavailable
   - 图文详情 / redirect 局部恢复后又反复回退
   - 根因不是微信，而是后端内部不稳定

## 2. 当前稳定边界
建议后续固定为：

### 2.1 API 层
职责：
- 接收 HTTP 请求
- 获取 `SessionLocal`
- 调用 service
- 统一处理 redirect / response

不再让 API 猜测 service 是否需要 db。

### 2.2 Service 层
职责：
- 纯业务逻辑
- 明确输入输出
- 不再混入临时 override block

### 2.3 文本推荐 / H5 / redirect
拆成三个边界：
- 推荐文本生成
- H5 详情渲染
- promotion redirect

三者之间只通过明确 helper 函数连接。

## 3. 后续重构建议
1. 把 `app/services/wechat_recommend_h5_service.py` 拆分成：
   - `wechat_recommend_text_service.py`
   - `wechat_recommend_page_service.py`
   - `wechat_recommend_selection_service.py`
   - `wechat_recommend_link_service.py`

2. 把推荐规则读取统一收敛到：
   - `app/services/wechat_recommend_rules_config_service.py`
   避免多个 helper 各自读 json

3. 把 recommendation exposure / cycle_pool / diversity 明确收敛成单一选择器模块

4. 把 promotion redirect 作为独立稳定链路，不再与页面渲染逻辑混改

## 4. 当前结论
当前优先级不是继续加功能，而是：
- 先稳定主链路
- 再做“更多同类产品公众号内直回”
- 最后再做推荐文案与用户画像优化


## 收敛决定（2026-04-16 dev）
- `app/services/wechat_recommend_runtime_service.py` 作为推荐链路唯一真实实现
- `app/services/wechat_recommend_h5_service.py` 降级为兼容导入壳，不再承载业务逻辑
- 后续所有推荐逻辑修改，必须只改 runtime_service


## 最终收敛决策（runtime 单一真源）
- 删除 `app/services/wechat_recommend_h5_service.py`
- 推荐文本、图文详情、更多同类产品、按用户轮次去重，全部以 `app/services/wechat_recommend_runtime_service.py` 为唯一真实实现
- 任何新功能不得再落到旧 H5 service 文件
- 后续若出现推荐链路问题，只排查：
  - `app/services/wechat_recommend_runtime_service.py`
  - `app/services/message_router.py`
  - `app/api/wechat_recommend_h5.py`
  - `app/api/promotion.py`

