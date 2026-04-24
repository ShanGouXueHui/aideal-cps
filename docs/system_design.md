# AIdeal CPS 系统设计（2026-04-17 authoritative）

## 1. 项目定位
AIdeal CPS（智省优选）是基于微信服务号的 AI 导购 + 京东联盟返佣系统，不是传统电商商城，不做自营交易闭环。

## 2. 环境与角色
- 开发环境：新加坡机器 `43.106.55.255`
- 开发用户：`cpsdev`
- 开发路径：`/home/cpsdev/projects/aideal-cps`
- 生产环境：杭州机器 `8.136.28.6`
- 生产用户：`deploy`
- 生产路径：`/home/deploy/projects/aideal-cps`
- 原则：默认开发、编码、验证都先在新加坡机器完成；杭州机器只用于最终部署与验收

## 3. 冻结边界
### 3.1 微信通信层冻结
- `app/api/wechat.py`
- `app/services/message_router.py`
- `app/services/wechat_service.py`

### 3.2 JD 通信层冻结
- `app/services/jd_union_client.py`
- promotion redirect 协议边界
- 基础 JD API 调用协议边界

### 3.3 允许演进的层
- runtime strategy layer
- recommendation selection layer
- user profile / behavior layer
- intent parsing layer
- H5 展示层
- partner business layer

## 4. 当前线上成功基线
- 菜单“今日推荐”已切换为单次被动 `news` 图文卡片
- 一次返回 3 个商品
- 每个商品可点击进入 H5 详情或下单链路
- 当前成功链路不再依赖客服消息二次 / 三次补发

## 5. 当前结构性问题
1. `today_recommend` 已统一到 runtime，但“找商品”自然语言请求尚未完全统一到底层 recommendation runtime / intent parsing 编排层
2. 当前去重仅为“当前轮次内不重复 + 池耗尽后轮转”，不等于商用月度去重
3. news item 的展示表达已经技术成功，但商业表达仍偏粗糙
4. URL 过长，短链接 / 短码尚未接入
5. 欢迎语与合伙人中心仍需商用化细化

## 6. 当前迭代顺序
1. 先修 docs / HANDOFF
2. 再优化 `today_recommend` news item 展示结构
3. 再接统一 intent / recommend orchestrator
4. 再做短链接、去重升级、欢迎语、合伙人中心细化

## 7. 数据联调注意事项
- 若开发机通过 SSH tunnel 连接生产库，必须先覆盖 `DATABASE_URL`
- 然后再 import app 的 settings / db 模块
- 否则 SQLAlchemy engine 会缓存旧配置，导致验证结果失真

## 8. 2026-04-18 当前新增系统能力
### 8.1 商品池刷新调度
- 生产当前已切换为 systemd timer 调度：
  - `aideal-catalog-refresh.timer`
  - `aideal-catalog-refresh.service`
- 巡检入口：
  - `ops/check_catalog_refresh_health.sh`
- 状态文件：
  - `run/catalog_refresh_status.json`

### 8.2 商品池治理
- `goods.query` 参数已与京东文档对齐
- keyword refresh 已修复 session 未提交状态下的重复插入问题
- `jd_sku_id` 已优先 numeric SKU，历史 non-numeric active 脏数据已做首轮归并清理

### 8.3 主动推荐池治理
- 当前“主动推荐池”不再等同于“所有 normal 商品”
- 已新增：
  - `config/proactive_recommend_rules.json`
  - runtime 主动推荐池配置过滤
- 当前设计原则：
  - 合规过滤解决“能不能展示”
  - proactive pool 过滤解决“适不适合主动推荐”

## 2026-04-19 微信正式回调域名切换完成
- CPS 正式域名 `aidealfy.cn` ICP 备案已完成，DNS 已解析到生产机 `8.136.28.6`
- 微信服务号服务器配置已从临时域名切换为：
  - `https://aidealfy.cn/wechat/callback`
- Nginx 已修复正式域名 `/wechat/callback` 反代路径：
  - `https://aidealfy.cn/wechat/callback` -> `http://127.0.0.1:8000/wechat/callback`
- Let's Encrypt 证书已签发：
  - `aidealfy.cn`
  - `www.aidealfy.cn`
- `certbot.timer` 已启用，`certbot renew --dry-run` 通过，证书自动续期闭环正常
- 临时域名 `aidealfy.kindafeelfy.cn` 暂保留 24-72 小时作为回滚通道，确认正式域名稳定后再删除解析和 Nginx block
- 微信消息加密方式当前继续保持“明文模式”
- 不要直接在微信后台切“安全模式”，当前代码尚未实现 `msg_signature` 校验、AES 解密、加密回复；后续需单独做 `feat(wechat): support encrypted callback mode`

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

<!-- START 2026-04-20 JD榜单驱动商品池刷新 -->
## 2026-04-20 JD榜单驱动商品池刷新

本次修正：不再用人工猜测方式扩主动推荐池白名单。上一轮“家庭日用品扩容白名单”已回滚，改为以京东接口实际榜单结果和生产库质量过滤结果反推主动推荐池范围。

### 已落地
1. `app/services/catalog_refresh_service.py`
   - `refresh_keyword_catalog` 支持 `keyword_sort_profiles`。
   - 同一关键词可按多个京东排序榜单拉取、去重、入库。
   - 入库 `ai_tags` 增加 `榜单:<profile>`，用于追踪来源。
2. `config/catalog_refresh_rules.json`
   - `keyword_seeds` 继续保留 41 个高频家庭消费关键词。
   - 新增榜单 profile：
     - `order_count_30d`：`sort_name=inOrderCount30Days`
     - `commission_amount`：`sort_name=commission`
3. `config/proactive_recommend_rules.json`
   - `include_category_keywords` 不再人工硬扩。
   - 当前值由生产库真实商品按合规、价格、佣金、销量、标题风险过滤后，从 Top 商品类目反推生成。
   - 质量阈值仍由配置控制：`min_effective_price`、`min_estimated_commission`、`min_sales_volume`。

### 本轮生产验证摘要
- JD 榜单候选数：174
- 主动推荐池数量：177
- 风险标题命中数：3
- 图文推荐条数：3
- 反推类目数：57
- 主要类目：牙膏、猫砂、洗碗机清洁剂、其他大米、狗干粮、卫生巾、漂白/彩漂、奶瓶清洗、洗衣凝珠、普通洗衣液、发膜、抹布/百洁布、湿厕纸、抽纸、垃圾袋、整套茶具、菜籽油、其他收纳袋、洗发水、茶饮料、洗脸巾、保温杯、葵花籽油、洗发沐浴、内衣洗衣液、陶瓷/马克杯、保鲜膜套、玻璃杯、洗洁精、保鲜盒

### Top 样例
- 牙膏｜合和泰蜂胶牙膏 双效优护牙膏 专利益生菌牙膏 抑菌清新口气 120g*5支｜佣金 85.16｜30天量 200
- 猫砂｜许翠花 经典原味纯植物猫砂2.5kg*4包木薯猫砂不粘底强吸水易结团｜佣金 14.29｜30天量 4000
- 洗碗机清洁剂｜亮碟 洗碗块洗碗粉洗碗盐 洗碗机专用清洁块漂洗剂耗材100块三合一｜佣金 15.3｜30天量 500
- 其他大米｜QIU MU SI TIAN江汉大米秋慕思田月牙香米10斤当季新米冷水灌溉优质原粮现货速发 玉泉贡米5KG真空装｜佣金 11.98｜30天量 40000
- 狗干粮｜比瑞吉狗粮爱不将就小型中大型金毛成犬狗粮牛肉味16kg添加鱼油原料透明｜佣金 16.35｜30天量 2000
- 卫生巾｜ABC瞬吸云棉轻薄透气日用卫生巾棉柔干爽防漏姨妈巾云般柔软 【瞬吸云棉】卫生巾9包｜佣金 9.12｜30天量 10000
- 漂白/彩漂｜优洁士 爆炸盐洗衣去污渍强婴儿彩漂粉漂白剂白色衣服免搓洗去黄增白剂 红石榴香：活氧爆炸盐1200g｜佣金 9.73｜30天量 4000
- 奶瓶清洗｜英氏（YEEHOO）奶瓶清洗剂婴儿玩具洗洁精宝宝洗奶瓶清洗液餐具果蔬清洁剂 【到手2瓶】奶瓶果蔬清洗剂498ml｜佣金 8.64｜30天量 5000

### 后续规则
- 商品池扩容优先改 `config/catalog_refresh_rules.json` 的关键词和榜单 profile。
- 主动推荐池白名单必须来自真实 JD 榜单结果 + DB 质量过滤，不允许凭主观类目直接扩。
- 用户行为数据积累后，再把“榜单分数 + CTR + 下单转化 + 佣金”合成统一排序分。
<!-- END 2026-04-20 JD榜单驱动商品池刷新 -->

<!-- START 2026-04-20 自动动态白名单机制 -->
## 2026-04-20 自动动态白名单机制

本次调整将主动推荐池白名单从“人工维护配置”升级为“夜间刷新后自动生成动态白名单”。

### 核心机制
1. 商品池刷新继续从京东接口按多个榜单 profile 拉取：
   - `order_count_30d`：30天下单量榜，`sort_name=inOrderCount30Days`
   - `commission_amount`：佣金金额榜，`sort_name=commission`
2. `app/services/proactive_whitelist_refresh_service.py` 负责在商品池刷新后自动生成：
   - `run/proactive_recommend_whitelist.json`
3. 运行时 `wechat_recommend_runtime_service` 会优先读取动态白名单：
   - 默认路径：`run/proactive_recommend_whitelist.json`
   - 配置入口：`config/proactive_recommend_rules.json`
4. 动态白名单来源标签：
   - `榜单:`：京东排行榜导入商品
   - `用户请求:`：后续用户搜索/请求沉淀商品可直接进入同一机制
5. 静态 `include_category_keywords` 仅作为动态文件缺失时的保守 fallback，不再作为长期人工白名单。

### 当前生产验证
- 动态白名单状态：success
- 候选商品数：169
- 动态类目数：56
- 主动推荐池数量：177
- 风险标题命中数：0
- 图文推荐条数：3
- 主要动态类目：猫砂、洗碗机清洁剂、其他大米、狗干粮、漂白/彩漂、奶瓶清洗、洗衣凝珠、普通洗衣液、发膜、抹布/百洁布、卫生巾、湿厕纸、垃圾袋、整套茶具、菜籽油、其他收纳袋、抽纸、洗发水、洗脸巾、保温杯、葵花籽油、洗发沐浴、内衣洗衣液、陶瓷/马克杯、保鲜膜套、玻璃杯、保鲜盒、婴童乳霜纸、洗脸巾/棉柔巾/压缩毛巾、保鲜膜、一次性清洁用品、洗护套装、桌面收纳盒、牙膏、花生油

### Top 样例
- 猫砂｜许翠花 经典原味纯植物猫砂2.5kg*4包木薯猫砂不粘底强吸水易结团｜佣金 14.29｜30天量 4000
- 洗碗机清洁剂｜亮碟 洗碗块洗碗粉洗碗盐 洗碗机专用清洁块漂洗剂耗材100块三合一｜佣金 15.3｜30天量 500
- 其他大米｜QIU MU SI TIAN江汉大米秋慕思田月牙香米10斤当季新米冷水灌溉优质原粮现货速发 玉泉贡米5KG真空装｜佣金 11.98｜30天量 40000
- 狗干粮｜比瑞吉狗粮爱不将就小型中大型金毛成犬狗粮牛肉味16kg添加鱼油原料透明｜佣金 16.35｜30天量 2000
- 漂白/彩漂｜优洁士 爆炸盐洗衣去污渍强婴儿彩漂粉漂白剂白色衣服免搓洗去黄增白剂 红石榴香：活氧爆炸盐1200g｜佣金 9.73｜30天量 4000
- 奶瓶清洗｜英氏（YEEHOO）奶瓶清洗剂婴儿玩具洗洁精宝宝洗奶瓶清洗液餐具果蔬清洁剂 【到手2瓶】奶瓶果蔬清洗剂498ml｜佣金 8.64｜30天量 5000
- 洗衣凝珠｜SUPILERS山茶花五合一洗衣凝珠持久留香抑菌除螨柔顺浓缩家用洗衣液留香珠 山茶花洗衣凝珠【60颗袋装】｜佣金 8.2｜30天量 1000
- 普通洗衣液｜立白大师香氛洗衣液玫瑰花香深层洁净护色持久留香72小时低泡易漂洗 立白大师香氛7件套｜佣金 4.49｜30天量 20000
- 普通洗衣液｜立白大师香氛香水洗衣液持久留香柔顺护衣玫瑰花香低泡易漂洗家用 立白洗护组合9件套｜佣金 4.49｜30天量 20000
- 发膜｜滋源【云旗代言】发膜防脱养护强韧发丝深层修护护发素235g头皮可用｜佣金 7.19｜30天量 3000

### 后续约束
- 不再手工扩 `include_category_keywords` 作为主机制。
- 扩容优先改 `keyword_seeds`、`keyword_sort_profiles`、质量阈值、风险过滤词。
- 用户请求沉淀后，只要商品 `ai_tags` 带 `用户请求:`，即可进入自动白名单候选。
- 每晚 systemd timer 执行商品池刷新时自动刷新动态白名单，运行时无需重启即可读取最新文件。
<!-- END 2026-04-20 自动动态白名单机制 -->

<!-- START 2026-04-20 免费LLM编排与动态白名单语义复核 -->
## 2026-04-20 免费LLM编排与动态白名单语义复核

### 目标
- CPS 不再把 Qwen / OpenRouter / Gemini / NVIDIA / Hugging Face / 智谱 / 百炼 / 混元 等 provider 调用散落在业务代码中。
- 新增独立免费 LLM 编排层：`app/services/free_llm/`。
- 商品池动态白名单不再靠人工白名单；先由京东下单榜 / 佣金榜 / 用户请求沉淀生成候选，再由免费 LLM 做语义复核。
- 免费 LLM 只做“删减/复核”，不能绕过硬合规规则，不能新增未出现在候选中的类目。
- 后续微信公众号自然语言导购、商品意图识别、商品重排、推荐理由生成，都复用同一 `free_llm` router。

### 新增模块
- `config/free_llm_provider_registry.json`
  - provider、endpoint、seed models、discovery 策略、cost_tier。
  - 不包含任何 secret。
- `config/free_llm_task_policy.json`
  - 不同任务的 provider 优先级、是否要求 JSON、是否允许 premium fallback。
- `app/services/free_llm/model_catalog_refresh_service.py`
  - 自动发现 provider 模型目录。
  - 对上百模型做初筛、打分、排序。
- `app/services/free_llm/health_probe_service.py`
  - 对候选模型探活。
  - 生成 `run/free_llm_active_routing.json`。
- `app/services/free_llm/router_service.py`
  - 统一调用入口。
  - 失败自动切换 provider / model。
  - 用户无感 fallback。
- `app/services/free_llm/semantic_review_service.py`
  - 商品池动态白名单语义复核。
  - 只允许删除风险/低质类目，不允许新增类目。
- `scripts/sync_free_llm_env.py`
  - 从 `.freeLLM` 同步 key 到 `.env`，只打印 key 名，不打印 secret。
- `scripts/refresh_free_llm_catalog.py`
- `scripts/probe_free_llm_health.py`
- `scripts/smoke_free_llm_router.py`

### 夜间任务集成
`run_nightly_catalog_refresh()` 顺序升级为：
1. 京东精选池刷新
2. 京东关键词池刷新
3. 过期 active 商品下线
4. inactive 陈旧商品清理
5. 免费 LLM model catalog refresh
6. 免费 LLM health probe / active routing
7. 动态主动推荐白名单刷新
8. 免费 LLM 语义复核白名单

### 高价值用户 premium fallback
- 普通任务默认免费模型优先。
- 累计 GMV >= 1000 RMB 的用户，后续自然语言导购可允许 Qwen Plus / Max 兜底。
- 当前商品白名单复核不启用 premium fallback，避免夜间任务无约束消耗付费模型。

### 配置治理原则
- secret 只允许在 `.env` / `.freeLLM`。
- provider、model seed、任务策略必须在 `config/`。
- 自动探活、模型目录、运行态路由在 `run/`，不提交。
- 调用日志在 `logs/free_llm_usage.log`，不提交。
- 业务服务不得直接调用单一 provider，必须通过 `free_llm.router_service`。
<!-- END 2026-04-20 免费LLM编排与动态白名单语义复核 -->

<!-- START 2026-04-20 免费大模型池完整探活与后台健康探测 -->
## 2026-04-20 免费大模型池完整探活与后台健康探测

### 当前结论
- 免费 LLM 完整探活已跑通：`mode=full`，`probe_count=86`，`success_count=42`。
- 可用 provider 包括 OpenRouter、NVIDIA、百炼、智谱、腾讯混元，以及 `qwen_premium` 兜底。
- Gemini 与 HuggingFace 当前在杭州生产环境探活失败或不可达，不作为当前主路由。
- `run/free_llm_active_routing.json` 已生成，业务侧后续应读取该文件做模型选择，不要在用户请求链路中逐个实时探活。

### 后台机制
- 新增后台探活 timer：
  - `ops/systemd/aideal-free-llm-health-probe.service`
  - `ops/systemd/aideal-free-llm-health-probe.timer`
  - `ops/systemd/run_free_llm_health_probe.sh`
  - `ops/check_free_llm_health.sh`
- 机制：后台定时刷新免费模型目录、探测模型可用性、时延、JSON 输出能力，并生成综合排序。
- 探活模式：
  - `quick`：快速验证。
  - `background`：生产后台持续探活。
  - `full`：低频完整探活，用于重新评估模型池。

### 使用原则
- 微信用户对话链路优先读取 `active_routing` 的已验证模型，失败后自动切下一个模型，用户无感。
- 高价值用户或高价值订单场景，允许使用 `qwen_premium` 作为付费兜底。
- `.freeLLM`、`.env`、运行日志、运行态 JSON 均不得进入 GitHub。
<!-- END 2026-04-20 免费大模型池完整探活与后台健康探测 -->

### 2026-04-20 调度口径修正
- Free LLM health probe 不应每 30 分钟跑一次完整探活，避免外部 provider 慢响应导致任务重叠或长期占用。
- 生产调度改为每天一次：`OnCalendar=*-*-* 04:20:00`，并设置 `RandomizedDelaySec=20m`。
- 用户请求链路不实时逐个探活，只读取 `run/free_llm_active_routing.json` 的已验证路由；失败时按路由自动切换下一个模型。
- 完整探活仅用于低频刷新模型池、淘汰失效模型、更新综合排序。

<!-- START 2026-04-20 免费LLM商品级白名单尾巴治理 -->
## 2026-04-20 免费LLM商品级白名单尾巴治理

本次收尾目标：解决动态白名单只做“类目级派生 / 类目级审核”，但未对进入主动推荐池的具体商品标题做语义级尾巴治理的问题。

已完成：
1. `app/services/free_llm/semantic_review_service.py`
   - 在原有 `review_proactive_categories_with_free_llm` 基础上，增加类目关键词归一能力：
     - 允许将京东细分类目归一为更短、更干净的中文关键词；
     - 仍禁止模型凭空新增无关类目；
     - 归一结果必须能从原始候选类目中找到语义锚点。
   - 新增 `review_proactive_products_with_free_llm`：
     - 输入高分候选商品样本；
     - 通过免费 LLM 输出需要拦截的 `product_id`；
     - 与规则侧的试用、拉新、低质引流、风险词拦截合并；
     - LLM 失败时 fallback 到启发式规则，不阻塞夜间刷新。

2. `app/services/proactive_whitelist_refresh_service.py`
   - 动态白名单生成流程升级为：
     - 京东销量榜 / 佣金榜采集；
     - DB 质量门槛过滤；
     - 类目归一与审核；
     - 商品级语义审核；
     - 输出 `run/proactive_recommend_whitelist.json`。
   - 新增输出字段：
     - `semantic_review`
     - `product_review`
     - `blocked_product_ids`

3. `app/services/wechat_recommend_runtime_service.py`
   - 主动推荐池 runtime 读取动态白名单中的 `blocked_product_ids`；
   - 被 LLM / 规则判定为不适合主动推荐的商品，即使类目命中白名单，也不会进入今日推荐 / 找商品入口。

设计原则：
- 免费 LLM 只做“语义质检 / 归一 / 拦截建议”，不直接绕过硬规则。
- 硬合规规则仍优先：药品、酒类、农药、防身、本地维修、成人情趣等继续由规则强拦截。
- 免费 LLM 不可凭空扩类目；只允许在京东榜单和用户请求沉淀出的候选范围内做清洗。
- 运行时只消费 `run/proactive_recommend_whitelist.json` 的确定性结果，避免用户点击菜单时同步等待 LLM。
- 夜间 systemd timer 继续负责后台刷新，用户无感。

下一步主线：
- 回到微信菜单优化：
  - 今日推荐图文入口；
  - 找优惠 / 搜商品自然语言统一 intent orchestrator；
  - 我的会员 / 我的订单 / 帮助说明。
<!-- END 2026-04-20 免费LLM商品级白名单尾巴治理 -->

<!-- START 2026-04-20 免费LLM白名单尾巴修正 -->
## 2026-04-20 免费LLM白名单尾巴修正

本次修正点：
1. `router_service.py`
   - JSON 任务优先选择探活结果中 `json_ok=true` 的模型；
   - 避免先命中“可回复但 JSON 不稳定”的免费模型，导致语义审核 fallback。

2. `semantic_review_service.py`
   - 增加确定性的类目归一兜底：
     - `厨房纸巾 -> 厨房纸`
     - `牙线/牙线棒/牙签 -> 牙线`
     - `洗脸巾/棉柔巾/压缩毛巾 -> 洗脸巾 / 棉柔巾`
     - `其他大米 / 长粒香米 / 稻花香米 -> 大米`
     - `菜籽油 / 花生油 / 葵花籽油 / 玉米油 -> 食用油`
     - `猫干粮 / 猫湿粮 -> 猫粮`
     - `狗干粮 -> 狗粮`
   - 即便免费 LLM 语义归一失败，也不会把京东细分类目小尾巴直接扩散到 runtime 白名单。

3. 验证脚本修正：
   - smoke 阶段在 DB session 关闭前完成属性读取；
   - 避免 SQLAlchemy `DetachedInstanceError` 干扰验收判断。

当前策略：
- 京东榜单 + 用户请求沉淀负责扩池；
- 硬合规规则负责底线过滤；
- 免费 LLM 负责语义质检和商品级审核；
- 确定性规则负责 LLM 失败时的兜底归一；
- runtime 只消费 `run/proactive_recommend_whitelist.json`，不在用户点击菜单时同步等待模型。
<!-- END 2026-04-20 免费LLM白名单尾巴修正 -->

<!-- START 2026-04-20 找商品菜单与自然语言商品需求图文化 -->
## 2026-04-20 找商品菜单与自然语言商品需求图文化

本次把菜单主线继续推进到“找商品”和用户自然语言商品需求：

1. 菜单 `找商品`：
   - 从纯文本入口升级为单次被动 `news` 图文卡片。
   - 卡片点击进入商品 H5 详情页，详情页继续提供下单链接和更多同类产品。
   - 仍保留文本兜底，避免商品池异常时空回复。

2. 文本商品需求：
   - 用户直接回复如“想买洗衣液，便宜一点，销量高一点”时，优先返回 1-3 条 `news` 图文卡片。
   - 选品复用现有商品池、合规过滤、成人限制拦截、京东实时搜索兜底和三商品选择逻辑。
   - 链接统一走 `/api/promotion/redirect` 或 H5 承接，保留 scene / slot / openid 归因。

3. 实时链路原则：
   - 微信被动回复不在同步链路里长时间调用免费 LLM，避免超过公众号回调窗口。
   - 免费 LLM 当前继续用于后台动态白名单、商品级审核、类目尾巴归一化和模型健康路由。
   - 后续若接用户实时 LLM，应采用低超时、失败即降级、必要时异步客服消息补充，不破坏回调主链路。

4. 验证结果：
   - `find_article_count > 0`
   - `text_article_count > 0`
   - `router_find_is_news = True`
   - `router_text_is_news = True`

下一步菜单主线：
- 优化“今日推荐”的多样性、疲劳度和类目去重。
- 继续细化欢迎语、帮助中心、合伙人中心。
<!-- END 2026-04-20 找商品菜单与自然语言商品需求图文化 -->

<!-- START 2026-04-24 商品请求精度与去重收尾 -->
## 2026-04-24 商品请求精度与去重收尾

针对“找商品 / 自然语言商品请求”图文化后的第一轮线上冒烟结果，本次继续做了一层精度与去重收尾：

1. 选品精度：
   - 在 `wechat_dialog_service.py` 中新增“未被用户明确请求的细分属性惩罚”。
   - 当前重点压制：`内衣 / 婴儿 / 宝宝 / 儿童 / 宠物 / 猫 / 狗 / 奶瓶 / 厨房` 等过细子场景误入主请求。
   - 例如用户只说“洗衣液”，不再优先混入“内衣洗衣液”。

2. 三商品选择逻辑：
   - `最符合你需求` 仍以综合偏好分为主。
   - `下单热度更高` 优先在不同类目/不同店铺候选中选。
   - `口碑与店铺更稳` 再做一层类目/店铺去重，减少 3 条候选过于相似。

3. 验证：
   - “想买洗衣液，便宜一点，销量高一点” 能返回 3 条 news。
   - `bad_innerwear_count = 0`
   - `router_text_is_news = True`

这一步完成后，菜单主线下一优先级回到：
- 今日推荐疲劳度治理
- 今日推荐类目/店铺/标题去重
- 欢迎语 / 合伙人中心商用化
<!-- END 2026-04-24 商品请求精度与去重收尾 -->

<!-- START 2026-04-24 主动推荐池确定性尾巴过滤 -->
## 2026-04-24 主动推荐池确定性尾巴过滤

背景：
- 4/24 定时任务巡检显示 catalog refresh 与 free LLM health probe 均正常。
- 商品池已扩展到 884 条，总体佣金池充足，但主动推荐池仍出现少量不适合主动推荐的尾巴商品。
- 本次不改微信通信边界，不改菜单主流程，只收紧主动推荐池确定性过滤。

巡检结论：
- `aideal-catalog-refresh.timer` 每日 03:15 正常执行。
- `aideal-free-llm-health-probe.timer` 每日执行，active routing 正常生成。
- 商品池：total=884，active=708。
- 活跃正常商品中，佣金数据充足：commission_ge_1=368，commission_ge_5=304，commission_ge_10=290。
- 动态白名单由 JD 下单榜 / 高佣榜 + 免费 LLM 生成，最新 category_count=30，tail_like_category_count=0。

本次修复：
- 在 `config/proactive_recommend_rules.json` 中追加主动推荐池排除规则。
- 重点排除：
  - 内衣 / 内裤 / 成人尿裤等偏私密商品。
  - 医用 / 药用 / 治疗 / 消炎等医疗风险商品。
  - 随机 / 颜色随机 / 香型随机 / 拍一发等低确定性尾货表达。
  - 维修 / 上门服务等不适合 CPS 主动推荐的服务商品。

注意：
- 这些规则仅用于主动推荐池，不代表自然语言搜索永远不能响应相关需求。
- 用户明确请求某类商品时，应由自然语言意图识别和合规过滤单独判断。
<!-- END 2026-04-24 主动推荐池确定性尾巴过滤 -->
