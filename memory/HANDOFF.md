# AIdeal CPS 当前续接锚点

## 一、项目身份
- 项目：AIdeal CPS（智省优选）
- 模式：微信公众号 / H5 驱动的 AI 导购返佣系统
- 核心：京东联盟导购媒体，不做自营交易闭环
- 当前开发分支：feat/wechat-official-account

## 二、开发环境
- 开发机：新加坡服务器
- 当前开发用户：cpsdev
- 开发路径：/home/cpsdev/projects/aideal-cps
- Git SSH：已打通
- Codex 工作模式：必须先读 docs + memory，再开始开发

## 三、生产环境
- 生产服务器：8.136.28.6
- 生产用户：deploy
- 生产路径：/home/deploy/projects/aideal-cps
- systemd：aideal.service
- Web：Nginx + FastAPI + uvicorn

## 四、当前确认过的关键事实
1. 微信当前真实回调路径：`/wechat/callback`
2. 当前不切 AES 安全模式
3. “今日推荐”已切换为**单次被动 news 图文卡片**主链路，不再依赖客服消息二次/三次补发
4. 当前线上成功基线定义为：
   - 被动回复
   - news 卡片
   - 3 个商品
   - 每个商品可点击进入 H5 详情或下单跳转链路
5. 当前通信链路冻结：
   - 微信 transport boundary 冻结
   - JD transport boundary 冻结
6. 当前推荐去重已实现的只是：
   - 当前轮次内不重复
   - 池耗尽后轮转
   这不是长期商用目标，后续需要升级为月度去重 / 疲劳度治理
7. 当前结构性缺口不是通信，而是：
   - `today_recommend` 已统一到 runtime
   - `find_product` 菜单入口已走 runtime
   - 用户自然语言商品请求尚未完全统一到底层 recommendation runtime / intent parsing 编排层

## 五、当前工程问题
1. 推荐/H5/redirect 曾被多轮临时修补，存在覆盖式修复历史
2. 同名函数重复定义风险高
3. 常量/路径/标签一度散落硬编码
4. 必须先做架构收口，再继续商用迭代

## 六、当前优先任务
1. 先修 docs / HANDOFF，使其成为新对话可信入口
2. 基于当前成功基线，仅在 `app/services/wechat_recommend_runtime_service.py` 内优化 `today_recommend` news 卡片展示结构
3. 统一“找商品”与自然语言商品请求到底层 recommendation runtime / intent orchestrator
4. 设计短链接、月度去重 / 疲劳度治理、欢迎语升级
5. 再继续细化合伙人中心、支付与收款闭环
6. 默认开发验证都先在新加坡机器完成，杭州机器只做最终部署与验收

## 2026-04-17 transport freeze boundary

当前已确认并固化的通信层冻结边界：

- 微信：`app/api/wechat.py`、`app/services/message_router.py`、`app/services/wechat_service.py`
- 推荐运行时主入口：`app/services/wechat_recommend_runtime_service.py`
- JD 通信模块：后续视为冻结边界，不允许业务需求直接侵入协议层

执行原则：

- 先保证通信链路稳定，再做推荐内容优化
- 任何“菜单点了 unavailable / 回调 500 / XML 异常 / route 签名漂移”都优先检查是否有人改动冻结边界
- 后续“今日推荐改 news / 图文卡片 / H5承接”属于业务层重构，不属于通信层

## 2026-04-17 通信边界冻结（WeChat/JD）
- 公众号通信基础链路冻结：`app/api/wechat.py` -> `app/services/message_router.py` -> `app/services/wechat_service.py`
- 京东通信基础链路冻结：`app/services/jd_union_client.py` 及其直接 API 边界
- 菜单点击“今日推荐”只允许单次被动回复；不再使用客服消息二次/三次补发
- 后续业务调整只允许落在推荐运行时、规则配置、文案、H5 展示层；不得直接改动微信/JD 通信边界
- 如需新增消息形态，必须新增独立适配层，不得在回调签名、消息路由、基础发包链路上继续叠 patch
- 当前阶段以“通信稳定优先”高于“内容形态丰富度”

## 2026-04-18 商品池治理 / systemd 调度 authoritative
- `jd.union.open.goods.query` 已完成参数修复并恢复可用：
  - wrapper 改为 `goodsReqDTO`
  - 显式传 `sceneId=1`
  - `sortName` 改为文档允许值 `inOrderCount30Days`
- 夜间商品池刷新已从 cron 切换到 systemd timer：
  - timer: `aideal-catalog-refresh.timer`
  - service: `aideal-catalog-refresh.service`
  - runner: `ops/systemd/run_catalog_refresh.sh`
  - 状态文件: `run/catalog_refresh_status.json`
  - 巡检脚本: `ops/check_catalog_refresh_health.sh`
- `catalog_refresh` 当前稳定能力：
  - `elite_refresh`
  - `keyword_refresh`
  - `inactive_cleanup`
  - `purge_cleanup`
- 当前启用关键词池：
  - 洗衣液
  - 牙膏
  - 抽纸
  - 宝宝湿巾
- 商品池治理已新增：
  - `jd_sku_id` 数字 SKU 优先归一化
  - 事务内去重，避免 `products.ix_products_jd_sku_id` 冲突
  - 合规规则收紧（维修/酒类/宠物药/农药/杀虫剂等）
  - proactive recommend pool 配置化过滤：`config/proactive_recommend_rules.json`
- 当前主动推荐池口径：
  - `status=active`
  - `allow_proactive_push=True`
  - `merchant_recommendable=True`
  - 通过 `config/proactive_recommend_rules.json` 做商用类目过滤
- 历史脏数据已清理：
  - active non-numeric `jd_sku_id` 已从 48 降到 2
  - 主动推荐池已从 72 收到约 38~41
- 当前主线已从“商品池修复”切回：
  1. 菜单 / today_recommend / H5 表达优化
  2. 找商品统一 intent/recommend orchestrator
  3. 再做短链接、疲劳度治理、欢迎语、合伙人中心细化

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

## 2026-04-19 配置治理规则补充
- 生产公开域名统一使用 `https://aidealfy.cn`
- `PUBLIC_BASE_URL` / `public_base_url` 必须来自 `.env` 或配置文件，不允许业务代码散落旧域名
- 关键词池、主动推荐池、合规词、推荐文案、H5 文案、阈值类参数优先放入 `config/*.json` 或数据库
- 代码中不得硬编码临时域名、业务阈值和可运营文案；如必须有默认值，只能作为无状态兜底，并同步写入 HANDOFF

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
