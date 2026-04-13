# AIdeal CPS 项目交接文档

## 1. 项目定位
AIdeal CPS（智省优选）是一个：
- 微信服务号/H5 驱动的 AI 导购返佣系统
- 商业模式核心是京东联盟导购媒体返佣
- 当前不是传统电商商城，不做自营交易闭环

## 2. 当前技术栈
- Backend: FastAPI
- DB: MySQL
- Migration: Alembic
- Deploy: Aliyun Ubuntu + systemd + Nginx
- Repo: GitHub 为唯一长期上下文载体

## 3. 当前工程原则
- 所有操作优先 copy-paste 可执行
- 不手工改文件，统一用 shell / heredoc
- 不在代码里明文写 secrets
- 所有 DB 变更必须经 Alembic
- 文档必须持续更新，优先信任 GitHub 文档而非聊天上下文
- 当前主链路先打通：商品查询 -> 转链 -> 点击归因 -> 订单查询/返佣

## 4. 部署信息
- Server user: deploy
- Project path: /home/deploy/projects/aideal-cps
- Codex auth path: /home/deploy/.codex/auth.json

## 5. 京东联盟 1.0 API 已确认规则
### 5.1 公共规则
- 入口: https://api.jd.com/routerjson
- 使用 method，不是 apiName
- 必传:
  - method
  - app_key
  - timestamp
  - format=json
  - v=1.0
  - sign_method=md5
  - sign
- 业务参数统一放在 360buy_param_json 中
- 签名算法:
  - 除 sign 外所有请求参数按 key 升序
  - 拼接 key + value
  - 前后包 appSecret
  - MD5 后转大写

### 5.2 已确认接口：jd.union.open.goods.jingfen.query
- 作用：查询精选商品 / 榜单 / 秒杀频道商品
- 当前可不依赖 access_token
- 正确业务参数结构：
  {
    "goodsReq": {
      "eliteId": 129,
      "pageIndex": 1,
      "pageSize": 20
    }
  }

### 5.3 已确认接口：jd.union.open.promotion.bysubunionid.get
- 作用：将商品链接 / 优惠券链接转为推广链接
- 正确业务参数结构：
  {
    "promotionCodeReq": {
      "materialId": "https://item.m.jd.com/product/100010793716.html",
      "siteId": "站点ID",
      "positionId": "推广位ID",
      "chainType": 2,
      "sceneId": 1
    }
  }
- 现阶段已确认：如果返回 403 无访问权限，则属于接口权限未生效或账号侧权限问题，不是签名错误

## 6. 当前系统下一阶段优先级
1. 重构 JD 1.0 通用调用器
2. 打通 jingfen.query
3. 打通 promotion.bysubunionid.get
4. 再对接订单查询
5. 最后把 AI 推荐和免费模型池真正接入业务流

## 7. Codex / 新对话使用方式
新对话先读取：
- docs/PROJECT_HANDOFF.md
- docs/JD_API_PROTOCOL.md
- docs/FREE_MODEL_POOL.md
- memory/HANDOFF.md


## 8. 京东联盟阶段性进展（已实测成功）
### 8.1 已验证成功接口
- jd.union.open.goods.jingfen.query
- jd.union.open.promotion.bysubunionid.get

### 8.2 已验证成功结果
- jingfen.query 可正常返回高佣榜商品数据
- promotion.bysubunionid.get 可正常返回 shortURL 短链
- 已经完成“查询商品 -> 转推广短链”的实网打通

### 8.3 当前代码落点
- 配置: app/core/jd_union_config.py
- 协议客户端: app/services/jd_union_client.py
- 工作流服务: app/services/jd_union_workflow_service.py
- smoke test:
  - scripts/jd_api_smoke_test.py
  - scripts/jd_top_goods_with_links.py


## 9. JD 内部 API（当前阶段）
已在现有 /jd router 基础上升级为可用内部接口：
- GET /jd/goods/top
- GET /jd/goods/top-with-links
- POST /jd/promotion/short-link

并增加本地轻缓存：
- 服务文件: app/services/jd_union_cache_service.py
- 缓存目录: data/jd_cache
- 默认 TTL: 900 秒


## 10. 商品结构化入库（进行中）
当前开始把 JD 榜单商品同步到 products 表，而不是只做临时查询。
本阶段新增内容：
- Alembic 迁移：补充 JD 商品字段
- 服务：app/services/jd_product_sync_service.py
- 路由：POST /jd/products/sync
- smoke test：scripts/jd_products_sync_smoke_test.py
