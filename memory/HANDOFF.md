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
