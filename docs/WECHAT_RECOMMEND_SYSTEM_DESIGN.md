# AIdeal CPS WeChat 推荐系统设计说明

## 1. 目标定位
智省优选不是普通电商站，而是“微信服务号 + 推荐消息 + 京东联盟转链 + 用户画像 + 数据驱动优化”的轻导购系统。

系统核心目标不是让用户在复杂页面里自己筛，而是：
1. 在微信对话里直接给出可下单商品；
2. 用更低决策成本提高点击和下单转化；
3. 逐步沉淀用户采购偏好与类目画像；
4. 后续通过免费大模型 + A/B 测试持续迭代推荐理由和模板。

## 2. 设计思想

### 2.1 先成交，再复杂化
当前阶段优先保证：
- 菜单“今日推荐”稳定返回 3 条被动 `news` 图文卡片
- 每条卡片都可点击进入 H5 详情或下单链路
- 通信链路不回退到客服消息补发
- 任何体验优化只落在 runtime / 文案 / H5 展示层
- 不为了业务改动重新打穿微信 / JD 通信边界

### 2.2 配置优先，避免硬编码
与业务强相关的常量不放在代码里反复覆盖，优先放到：
- `config/wechat_recommend_rules.json`
- 后续迁移到数据库 / 管理后台

当前已配置化内容包括：
- 推荐场景参数
- 去重策略
- 文案标签
- H5 详情路径
- promotion redirect 路径

### 2.3 推荐逻辑不是单纯比价
推荐排序要综合：
- 价差 / 折扣率
- 销量
- 评论量
- 好评率
- 店铺质量
- 主动推荐合规性

系统不追求“最大折扣”单一维度，而追求“更容易被用户接受和下单”的综合排序。

### 2.4 推荐理由要服务转化
推荐理由不是测试占位文案，而是偏商用的话术，围绕：
- 损失厌恶
- 占便宜心理
- 从众心理
- 降低决策成本
- 省时省心

后续会进一步按类目、价格带、用户画像做差异化生成。

### 2.5 去重正在从“当前轮次”升级到“商用疲劳度治理”
当前已实现：
- 同一用户
- 同一场景
- 当前轮次内不重复
- 池耗尽后立即轮转

下一阶段目标：
- 商品级 / SPU级 / 品类级 / 店铺级 / 用户级 去重
- 非主动搜索场景下，月度疲劳度治理优先
- 用户主动明确搜索时，可突破部分品类冷却，但仍保留 SKU / 近重去重

## 3. 当前实现结构

### 3.1 主入口
- 微信消息入口：`/wechat/callback`
- 微信通信边界：`app/api/wechat.py` -> `app/services/message_router.py` -> `app/services/wechat_service.py`
- 推荐运行时主入口：`app/services/wechat_recommend_runtime_service.py`
- 图文详情页：`/api/h5/recommend/{product_id}`
- 更多同类产品页：`/api/h5/recommend/more-like-this`
- 下单跳转：`/api/promotion/redirect`

说明：
- 当前 `today_recommend` 已走 runtime + news 卡片链路
- “找商品”菜单入口已走 runtime
- 用户自然语言商品请求尚未完全统一到底层 intent + recommend orchestrator

### 3.2 关键数据表
- `products`
- `click_logs`
- `wechat_recommend_exposures`
- `users`
- `user_profile`

### 3.3 当前推荐链路
1. 从商品池筛 active + 可主动推荐 + 有短链 + 有价格对比数据的商品
2. 计算综合分
3. 按用户历史曝光做当前轮次去重
4. 同批次优先做类目去重
5. 生成：
   - 推荐理由
   - 图文详情链接
   - 下单链接
   - 更多同类产品链接

## 4. 当前进展

### 已实现
- 微信回调链路稳定
- “今日推荐”已切换为被动 `news` 图文卡片
- 一次返回 3 个商品
- 卡片点击进入 H5 详情页
- 下单链路与 more-like-this 链路已接在 runtime 层
- 当前轮次去重已恢复
- runtime 模块已从历史大文件中切出，成为后续主落点

### 已验证
- 生产日志已出现 `today_recommend passive-news branch`
- 微信真实界面已显示 3 条图文卡片
- 当前成功链路不再依赖客服消息二次 / 三次补发
- 通信边界冻结原则已形成文档共识

### 当前不足
- news item 的商业表达仍偏粗糙，未收敛到“标题=商品名，描述=节约价格/到手价 + 热销数”
- “找商品”与自然语言商品请求尚未统一到底层 recommendation runtime / intent parsing 编排层
- 当前去重仍偏“当前轮次”，尚未升级为月度疲劳度治理
- URL 仍然偏长，尚未切到短码 / 短链接方案
- 欢迎语、合伙人中心仍处于可用但不够商用的状态

## 5. 下一阶段路线
1. 先修 docs / HANDOFF，确保新对话续接入口可信
2. 仅在 `app/services/wechat_recommend_runtime_service.py` 内优化 `today_recommend` news item 展示结构：
   - 第一行显示商品名
   - 第二行显示“节约价格 / 到手价 + 热销数量”
3. 新增商品意图识别模块与统一 recommendation orchestrator
4. 引入短码 / 短链接与月度去重 / 疲劳度治理
5. 升级欢迎语与合伙人中心，但不改动微信 / JD 通信边界

## 4.1 2026-04-18 商品池与主动推荐池更新
### 已新增
- `goods.query` 已恢复为可用关键词补池来源，但仍视为商品池支路，不替代通信边界稳定性原则
- `config/proactive_recommend_rules.json` 已上线，用于将“主动推荐池”与“普通可见商品池”分层
- `wechat_recommend_runtime_service.py` 的 `_active_recommend_products()` 已接入：
  - 合规可主动推荐过滤
  - 商用类目配置过滤
- `today_recommend` 当前推荐源已经不再只是“安全”，而是进一步偏向更适合微信内主动推荐的消费品池

### 已完成的商品池治理
- `jd_sku_id` 优先 numeric SKU
- keyword refresh 事务内去重
- 历史 non-numeric active 脏数据已做首轮退役
- 高风险类目已通过 compliance 规则打标并从主动推荐池剔除

### 当前口径
- 入库 != 可主动推荐
- `elite_refresh` 会继续同步更广商品集，但 runtime 主动推荐只读取过滤后的池
- 菜单“今日推荐”当前基于过滤后的主动推荐池生成 3 条 news 图文卡片

<!-- START 2026-04-19 商品池关键词扩容与主动推荐池质量过滤 -->
## 2026-04-19 商品池关键词扩容与主动推荐池质量过滤

### 已完成事项

1. 夜间商品池刷新关键词已从少量测试词扩展为 20 个正式商用品类词：
   - 洗衣液、牙膏、抽纸、宝宝湿巾、卷纸、厨房纸、垃圾袋、洗洁精、洗手液、沐浴露、洗发水、护发素、卫生巾、湿厕纸、保鲜袋、保鲜膜、收纳盒、水杯、毛巾、猫砂

2. 生产配置已提交：
   - `config/catalog_refresh_rules.json`
   - `keyword_sync_limit = 10`
   - `goods_query_sort_name = inOrderCount30Days`
   - `goods_query_sort = desc`
   - commit: `485587d`

3. 主动推荐池已增加商用质量过滤：
   - 配置文件：`config/proactive_recommend_rules.json`
   - 过滤试用、体验、便携、随身、小样、随机发、新人/拉新等不适合主动推送的商品
   - 增加最低有效价、最低预估佣金、最低销量约束
   - 代码位置：`app/services/wechat_recommend_runtime_service.py`
   - commit: `7929e40`

4. 生产验证结果：
   - `aideal.service` 已重启并正常运行
   - 主动推荐池数量：22
   - `bad_title_count = 0`
   - 20 个关键词刷新已生效
   - manual refresh 中 `keyword_refresh total = 178`

### 当前设计口径

- `products` 表是商品候选池，不要求所有 active 商品都能主动推送。
- 主动推荐必须通过更严格的 `_active_recommend_products()` 和 `config/proactive_recommend_rules.json` 过滤。
- 合规过滤、质量过滤、URL 域名、文案模板都必须走配置文件或数据库，禁止把业务常量散落在代码里。
- 生产公开域名统一使用 `https://aidealfy.cn`。
- 临时域名 `aidealfy.kindafeelfy.cn` 只作为短期回滚通道，后续确认稳定后删除 DNS 和 Nginx block。

### 后续待做

1. 增加商品池刷新 JSON 日志结构化输出，避免 sed/tail 截断导致 JSON 解析失败。
2. 将主动推荐池评分规则继续配置化或 DB 化：
   - 价格权重
   - 佣金权重
   - 销量权重
   - 店铺健康分权重
   - 类目多样性权重
3. 菜单优化主线继续：
   - 今日推荐图文入口
   - 找优惠 / 搜商品入口
   - 我的会员 / 我的订单 / 帮助说明

<!-- END 2026-04-19 商品池关键词扩容与主动推荐池质量过滤 -->
