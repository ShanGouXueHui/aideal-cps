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
