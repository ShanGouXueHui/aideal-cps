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
