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


## 11. 商品池查询能力（进行中）
现有 /products 已开始升级为 JD 商品池查询接口，新增筛选维度：
- elite_id
- elite_name
- shop_name
- min_commission_rate
- has_short_url
- order_by
- sort

当前目标：
- 后台可直接查高佣榜 / 今日必推 / 其他榜单商品池
- 为微信/H5 选品承接提供数据库查询能力


## 13. 商家画像与推荐原则（新增）
- 智省优选不是单纯追高佣，而是“用户价值优先、商业价值第二”
- 当前开始引入 merchant_profiles 与商家风险过滤
- 高风险商家默认不推荐，除非后续识别为独家供给
- 推荐排序升级为：
  - 用户价值分
  - 商家健康分
  - 商业价值分
- 当前 P0 先做：
  1. 商家画像
  2. 欢迎流
  3. 三商品推荐
  4. 点击归因跳转网关


## 14. 公众号对话层升级（进行中）
当前从“手机 / 家电关键词回复”升级为：
- 欢迎语引导
- 购物意图识别
- 商品池优先召回
- 三商品推荐（最符合 / 下单热度更高 / 口碑与店铺更稳）
- 非购物问题礼貌回转卖货场景

当前第一版先用规则和数据库商品池驱动，后续再接免费模型池 / Qwen 做排序与话术增强。


## 15. 公众号文案配置化（进行中）
- 欢迎语、帮助文案、非购物回转文案、兜底文案不再写在业务代码里
- 当前先放在 config/wechat_dialog_copy.json
- 后续再升级为数据库可配置 + admin 编辑


## 16. 冷启动兜底策略（更新）
- 当前商品池较小，未命中时不再乱推不相关商品
- 第一版策略：
  - 命中则返回 3 商品
  - 未命中则诚实提示“当前商品池未覆盖该品类”
  - 引导用户补充条件或稍后再问


## 17. 点击归因跳转网关（进行中）
当前开始把 /api/promotion/redirect 升级为真正的点击归因网关：
- 先记录 click_logs
- 再 302 跳到 JD 短链 / product.short_url
- 写入 scene / slot / trace_id / user_agent / referer / final_url
- 为订单归因、A/B 测试、用户画像更新做基础


## 18. 用户画像与 8:00 推荐最小版（进行中）
当前开始落地：
- users 表扩展用户画像基础字段
- 文本消息驱动画像更新
- 点击行为回流画像更新
- 8:00 推荐先生成候选消息，不直接发送
- 当前画像字段：
  - 价格偏好
  - 质量偏好
  - 销量偏好
  - 自营偏好
  - 偏好品类


## 19. 海报卡与晨推作业（进行中）
当前开始落地：
- 商品推荐海报卡 SVG 生成
- 晨推候选批次 job.json 输出
- 晨推脚本 run_morning_push_job.py
- cron 安装脚本 install_morning_push_cron.sh（先生成，未执行）


## 20. 合伙人归因基础版（进行中）
当前新增设计：
- 合伙人账号 partner_accounts
- 合伙人商品资产 partner_share_assets
- 合伙人点击日志 partner_share_clicks
- 一键购买永远在合伙人视图中排第一
- 分享分发第二，收益展示第三
- 所有分成比例与等级门槛放在 config/partner_program_rules.json


## 21. 合伙人分享资产包（进行中）
P2 已补充：
- buy_copy / share_copy
- buy_qr_svg_path / share_qr_svg_path
- poster_svg_path
- j_command_short / j_command_long 预留
- 合伙人视图保持“一键购买优先，分享第二”


## 22. 合伙人收益账本基础版（进行中）
P3 当前新增：
- partner_reward_ledgers
- estimated / settled / reversed / redeem / adjustment 事件
- tier 自动升级
- /api/partner/overview 概览接口
- 仍坚持先做积分账本，不做现金提现


### P3 规则补充
- 等级升级按累计已结算正向佣金，不因后续小额退货降级
- 积分当前仅限站内权益与服务抵扣，不支持现金提现
- 合伙人开通规则补充：支持 100 元开通门槛（规则已入配置）


## 23. 积分消耗最小闭环（进行中）
当前新增：
- partner_point_redemptions
- 100元合伙人开通/续费消费项
- redemption options / preview / commit / history
- activation_fee_paid / activation_fee_paid_at / activated_via


## 24. 合伙人中心最小可用版（进行中）
当前新增：
- /api/partner/center
- 聚合 profile / reward_overview / redemption_options / redemption_history
- recent_assets / recent_shareable_products
- monetization_closure 区块，前台可直接显示开通闭环


## 25. 合规治理与年龄分流基础版（进行中）
当前新增：
- products: compliance_level / age_gate_required / allow_proactive_push / allow_partner_share / compliance_notes
- users: adult_verified / adult_verified_at / verification_source
- 商品入池自动合规打标
- 晨推 / 对话 / 商品池 / 合伙人分享统一过滤
- 先做 adult_verified 预留，不依赖微信直接返回年龄字段


## 26. adult_verified 最小闭环（进行中）
当前新增：
- /api/user/adult-verification/status
- /api/user/adult-verification/declare
- /h5/adult-verify
- 未声明成年用户：restricted 商品只返回声明引导，不直接给商品
- 已声明成年用户：restricted 商品可被动查看，但仍不主动推荐、不做合伙人分享


## 27. 实名 / 年龄核验后置规划
读取：
- docs/REALNAME_VERIFICATION_ROADMAP.md

当前口径：
- self_declaration_h5 仅为技术预留
- 真正开放 restricted 商品前，应接入更强实名/年龄核验能力
- 优先评估国家网络身份认证公共服务，其次阿里云实人认证


## 28. 真实搜索可用升级（进行中）
当前新增：
- live JD keyword search fallback
- 本地商品池不足时，自动走 jd.union.open.goods.query
- 仍保留合规过滤 / adult gate / 高风险过滤
- 微信回复优先返回 3 个真实可买链接


## 29. 商品池治理原则（新增）
- 本地商品池不足时，可回退 JD 实时搜索
- 但长期商用主模式应为：夜间后台刷新商品池 + 白天优先命中本地池
- 后续需增加：
  - 夜间补池任务
  - 商品有效期/最后同步时间治理
  - 过期商品清理与降权


## 30. 夜间商品池刷新任务骨架（进行中）
当前新增：
- config/catalog_refresh_rules.json
- catalog_refresh_service
- run_nightly_catalog_refresh.py
- 夜间精选榜刷新
- 夜间关键词补池
- 过期商品 inactive
- 长时间失效且无引用商品 purge


## 31. 夜间刷新 cron 调度
- 安装脚本：scripts/install_catalog_refresh_cron.sh
- 当前 cron：每日 03:15 执行 run_nightly_catalog_refresh.py
- 使用 flock 防重入
- 日志输出到 logs/catalog_refresh.log
