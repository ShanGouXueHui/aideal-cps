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
- 开发环境：新加坡机器 `43.106.55.255`
- 开发用户：`cpsdev`
- 开发路径：`/home/cpsdev/projects/aideal-cps`
- 生产环境：杭州机器 `8.136.28.6`
- 生产用户：`deploy`
- 生产路径：`/home/deploy/projects/aideal-cps`
- systemd：`aideal.service`
- 注意：默认开发、编码、验证都先在新加坡机器完成；杭州机器只用于最终部署与验收

## 4.1 2026-04-17 工程续接校准（当前 authoritative）
- 当前线上成功基线：
  - 菜单“今日推荐” -> 单次被动回复
  - 消息形态 = `news` 图文卡片
  - 一次返回 3 个商品
  - 每个商品点进去进入 H5 详情或下单链路
- 当前冻结边界：
  - 微信通信基础链路：`app/api/wechat.py` -> `app/services/message_router.py` -> `app/services/wechat_service.py`
  - 推荐运行时主入口：`app/services/wechat_recommend_runtime_service.py`
  - JD 通信基础链路：`app/services/jd_union_client.py` 及其直接 API 边界
- 当前允许改动层：
  - runtime strategy layer
  - recommendation selection layer
  - user profile / behavior layer
  - intent parsing layer
  - H5 展示层
  - partner business layer
- 当前优先级已改为：
  1. 修 docs / HANDOFF，使其成为新对话可信入口
  2. 优化 `today_recommend` news item 展示结构
  3. 统一“找商品”与自然语言商品请求到底层 recommendation runtime / intent orchestrator
  4. 再做短链接、去重升级、欢迎语、合伙人中心细化

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
1. 修正文档与 HANDOFF，固化开发/生产角色、成功基线、冻结边界和下一阶段优先级
2. 仅在 `app/services/wechat_recommend_runtime_service.py` 内优化“今日推荐” news 卡片展示结构
3. 新增商品意图识别与统一 recommendation orchestrator，让“找商品”菜单入口和自然语言文本入口共享底层选品框架
4. 建立短链接与月度去重 / 疲劳度治理，但不得改动微信 / JD 通信基础链路
5. 合伙人中心继续沿“分享分发 + 收益账本 + 支付开通”方向细化，支付密钥仍只放本地 `.env`

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


## 32. 推荐口径统一与菜单配置
- recommendation_guard_service.py：统一主动推荐 / 合伙人分享 / 用户主动搜索的准入规则
- wechat_menu_entries.json：固定三入口菜单配置
- wechat_menu_service.py：菜单文案回复服务
- 下一步：将菜单 key 接入 message_router / 微信 CLICK 事件


## 33. message_router 已接入菜单入口
- CLICK 事件支持菜单 key：找商品 / 今日推荐 / 合伙人中心
- 文本消息先判断菜单关键词，再进入导购链路
- 下一步可继续把“今日推荐”升级为动态推荐，而不是静态回复


## 34. 今日推荐已接入真实商品池
- today_recommend_service.py：从真实商品池生成菜单“今日推荐”回复
- message_router.py：文本关键词/CLICK 事件触发今日推荐时走动态服务
- 当前仍是文本输出，下一步可升级成图文/海报卡片


## 35. 合伙人中心已接入动态摘要
- partner_center_entry_service.py：生成合伙人中心入口摘要
- message_router.py：文本关键词/CLICK 事件触发“合伙人中心”时走动态摘要
- 下一步可接积分、素材、分享商品、续费四个子入口


## 36. 合伙人中心二级动作已接入
- partner_center_action_service.py：
  - 积分
  - 素材
  - 分享商品
  - 续费
- message_router.py：文本与 CLICK 事件都可直接触发二级动作
- 下一步建议接“分享商品 + 商品名 -> 生成专属分享素材”


## 37. 分享商品 + 商品名 已接入
- partner_share_entry_service.py：
  - 解析“分享商品 + 商品名”
  - 从商品池筛选适合分发的商品
  - 返回买/分享摘要
- message_router.py：文本消息先尝试分享商品专属链路，再走合伙人中心二级动作


## 38. 分享商品已增强为素材包摘要
- partner_share_entry_service.py：
  - 返回买链接 / 分享链接
  - 返回海报与二维码路径
  - 返回购买文案 / 分享文案
  - 返回 asset_token / partner_code
- 下一步可继续把素材包摘要映射为真正的文件下载/查看入口


## 39. 素材包查看入口已接入
- partner_material_bundle_service.py：素材包清单与文件解析
- partner_materials.py：素材包清单接口 + 文件查看接口
- partner_share_entry_service.py：分享商品回复已带素材包入口


## 40. 公众号菜单同步能力已接入
- wechat_menu_sync_service.py：负责读取菜单配置、获取 token、创建菜单、查询当前菜单
- sync_wechat_menu.py：一键同步脚本
- 下一步：在线上用真实公众号凭证执行一次菜单同步

<!-- BEGIN: WECHAT_MP_STAGE_2026_04_15 -->
# WeChat MP阶段交接（2026-04-15）

## 一、当前项目与环境
- 项目：AIdeal CPS（智省优选）
- GitHub仓库：`git@github.com:ShanGouXueHui/aideal-cps.git`
- 当前主开发分支：`feat/wechat-official-account`
- 服务器主机：`iZbp116q1d1ucbio1ms235Z`
- 项目路径：`/home/deploy/projects/aideal-cps`
- Python虚拟环境：`/home/deploy/projects/aideal-cps/venv`
- systemd服务：`aideal.service`
- 启动方式：`uvicorn main:app --host 0.0.0.0 --port 8000`
- Nginx临时域名：`aidealfy.kindafeelfy.cn`
- 正式域名：`aidealfy.cn`（ICP备案完成后切回）
- 官网静态站仓库：`https://github.com/ShanGouXueHui/aideal-site`

## 二、微信公众号当前已打通状态
### 1）消息推送
- 微信后台消息推送 URL 已成功配置
- 当前生效 URL：`https://aidealfy.kindafeelfy.cn/wechat/callback`
- 当前回调真实后端路由：`/wechat/callback`
- 注意：不是 `/api/wechat/callback`

### 2）加密模式
- 当前模式：**明文模式**
- `.env` 中已配置：
  - `WECHAT_TOKEN`
  - `WECHAT_ENCODING_AES_KEY`
  - `WECHAT_MSG_ENCRYPT_MODE=plaintext`
- 说明：AES Key 只是已存储，**服务端还未实现 AES 解密/加密回复**，因此现在不能切“安全模式”。

### 3）HTTPS
- `aidealfy.kindafeelfy.cn` 已通过 `certbot --webroot` 成功签发证书
- 证书路径：
  - `/etc/letsencrypt/live/aidealfy.kindafeelfy.cn/fullchain.pem`
  - `/etc/letsencrypt/live/aidealfy.kindafeelfy.cn/privkey.pem`
- 已启用 HTTPS
- 自动续期已由 certbot 配置完成

### 4）Nginx站点
- 站点配置文件：
  - `/etc/nginx/sites-enabled/aidealfy-kindafeelfy.conf`
- 当前专用 access log：
  - `/var/log/nginx/aidealfy_kindafeelfy_access.log`

## 三、菜单与事件路由当前状态
### 1）当前菜单
- 找商品
- 今日推荐
- 合伙人中心

### 2）菜单已验证打通
已经通过结构化日志验证三条菜单链路：

- `找商品` -> `find_product_entry`
- `今日推荐` -> `today_recommend`
- `合伙人中心` -> `partner_center_entry`

### 3）结构化日志已生效
当前 `app/api/wechat.py` 已加入微信入站/出站日志，示例日志：

- `wechat inbound | msg_type=event event=CLICK event_key=找商品 ... matched_handler=find_product_entry`
- `wechat outbound | ...`

已验证可在以下位置观察：
- 应用日志：`sudo journalctl -u aideal.service -f --no-pager`
- Nginx日志：`sudo tail -f /var/log/nginx/aidealfy_kindafeelfy_access.log`

## 四、当前已经确认的业务结论
1. 菜单点击、文本消息、微信回调、HTTPS链路都已经正常
2. 现在不是“服务端没打通”的问题，而是进入**体验优化/转化优化**阶段
3. 当前“今日推荐”“找商品”仍偏文本型，下一阶段应升级为**图优先、点击直达京东**
4. 用户明确要求：
   - **优先图，不优先长文本**
   - **不要先跳海报页/H5，再跳京东**
   - **消息里直接展示图**
   - **用户点击后尽量直接去 JD 短链**
   - 目标是减少点击层级，提高转化率

## 五、下一阶段明确任务（新对话继续做）
### 任务A：将“找商品”改为图优先承接
目标：
- 菜单点击“找商品”后，不只是提示用户输入
- 直接返回 1 条带图的推荐卡片
- 点击卡片直达 JD 短链
- 同时保留一句轻量引导：用户也可以直接回复“卫生纸 / 洗衣液 / 宝宝湿巾 / 京东自营”等关键词

### 任务B：将“今日推荐”改为图优先承接
目标：
- 不再优先纯文本
- 优先返回带图消息
- 点击直达 JD 短链
- 推荐理由必须由 **JD真实数据** 驱动

### 任务C：推荐理由模板化
必须遵循：
- **事实层**：只能使用 JD 真实字段，如：
  - `sales_volume`
  - `price`
  - `coupon_price`
  - `short_url`
  - `image_url`
  - 店铺名 / 是否自营 / 商家质量分（若已入库）
- **话术层**：可以用心理学包装，但不能虚构事实
- 禁止伪造：
  - “京东Top XX”
  - “销量第X名”
  - “五星好评X人”
  - “近10天销量增长”
  - 任何接口未提供的排名/时效/人数

可用心理触发方向：
- 从众
- 损失厌恶
- 占便宜
- 效率/决策减负
- 体面/品质感
- 共情

### 任务D：图的来源策略
目标优先级：
1. **优先已有可直接展示的海报图/物料图**
2. 如果现有物料是 SVG 且不能稳定作为公众号图文封面，则退回使用 JD 商品主图
3. 点击仍然直接去 JD，不走海报页

### 任务E：安全收尾
高优先级后续任务：
- 封禁 `/.git` 等敏感路径
- 修复未知路径过宽返回 200 的问题
- 收紧 Nginx 静态站与动态服务边界

## 六、继续开发时必须遵循的沟通与工程要求
- 中文交流
- 职业化、直接、结构化表达
- 给 **copy-paste 可执行命令**
- **不要要求手工改文件**
- Linux 命令里**不要使用 `set -e`**
- 默认通过 **Codex + GitHub docs** 续接上下文
- 新对话开始时，先读：
  - `docs/PROJECT_HANDOFF.md`
  - `docs/PRODUCTION_PRODUCT_PLAN.md`
- 以 GitHub 仓库内容为准，而不是只依赖聊天短期上下文

## 七、当前服务端关键定位点
- 微信回调入口：`app/api/wechat.py`
- 菜单事件总路由：`app/services/message_router.py`
- 今日推荐：`app/services/today_recommend_service.py`
- 找商品推荐主流程：`app/services/wechat_dialog_service.py`
- 菜单配置：`config/wechat_mp_menu.json`
- 菜单同步脚本：`scripts/sync_wechat_menu.py`
- 微信图文/文本回复能力：`app/services/wechat_service.py`

## 八、已验证命令（可复用）
### 查看菜单事件日志
- `sudo journalctl -u aideal.service -f --no-pager`
- `sudo tail -f /var/log/nginx/aidealfy_kindafeelfy_access.log`

### 菜单同步（注意先导出环境变量）
- `export WECHAT_MP_APP_ID="$(grep '^WECHAT_MP_APP_ID=' .env | cut -d= -f2-)"`
- `export WECHAT_MP_APP_SECRET="$(grep '^WECHAT_MP_APP_SECRET=' .env | cut -d= -f2-)"`
- `PYTHONPATH=/home/deploy/projects/aideal-cps python -m scripts.sync_wechat_menu`

<!-- END: WECHAT_MP_STAGE_2026_04_15 -->


## 2026-04-16 22:11:10 推荐链路修正与模板商用化更新

### 已处理
- 接入 `app.api.wechat_recommend_h5` 路由，修复 `/api/h5/recommend/{product_id}` 未挂载导致的 404。
- 推荐文案恢复为商用模板：
  - 标题保留 `🔥 今日推荐 3 个，可直接购买：`
  - 商品编号与第一行同一行：`【1】商品标题`
  - 保留 `图文详情`、`下单链接`
  - 新增 `更多同类产品`
- 推荐理由从固定测试文案切回“行为心理驱动”口径：
  - 占便宜 / 损失厌恶
  - 从众 / 降低决策成本
  - 省时省心
- 推荐池继续采用：
  - `cycle_pool`
  - 同一用户、同一场景、当前轮次内不重复
  - 池耗尽后立即轮转
- 增加同批类别去重，优先避免同一批连续出现多个同类商品。
- 为 `/api/promotion/redirect` 增加异常日志，方便定位 500。

### 当前约束
- `goods.query` 仍未恢复为可用拉新主入口，夜间刷新先维持 `jingfen.query` 已验证链路。
- 商品池当前有效短链商品数仍偏少，类目去重与跨轮次多样性会受库存池规模影响。
- “更多同类产品”当前为 H5 页，先返回同类 3 个；后续可升级成公众号内二次消息回复链路。

### 下一步建议
1. 单独修复 `/api/promotion/redirect` 500 的根因，重点看：
   - `app/services/click_redirect_service.py`
   - `product.short_url / material_url / product_url`
   - JD 转链兜底逻辑
2. 将推荐理由生成逻辑下沉到配置 + 免费模型优化任务：
   - 基于点击率 / 下单率 / 收藏率做 AB
   - 文案按类目、人群、价格带自动细分
3. 将“更多同类产品”升级为公众号点击后直接回 3 条同类商品，而不是先跳 H5。
4. 扩大稳定商品池，继续走 `jingfen.query + short_url` 的可用链路。


## 2026-04-16 22:18:15 微信推荐系统阶段进展补充

### 设计思想已文档化
新增：
- `docs/WECHAT_RECOMMEND_SYSTEM_DESIGN.md`

该文档统一沉淀了：
- 微信推荐系统目标定位
- 配置优先原则
- 推荐排序设计
- 推荐理由的商用心理逻辑
- 当前轮次去重而非长期锁死
- 当前实现结构、进展、待修问题与下一阶段路线

### 本轮结论
- 推荐文本主链路已经恢复
- 当前轮次去重有效
- 图文详情、下单链接、更多同类产品三类入口都已生成
- 但 H5 详情页仍存在 500 风险点
- more-like-this 需要固定静态路由优先级
- promotion redirect 仍需继续做线上稳定性排查


## 2026-04-16 22:21:52 redirect alias 与同类页透传 openid 修正

### 已修复
- promotion redirect 同时支持：
  - `/promotion/redirect`
  - `/api/promotion/redirect`
- 解决推荐文本里使用 `/api/promotion/redirect` 但服务只暴露 `/promotion/redirect` 的不一致问题
- `more-like-this` H5 页面下单链接已透传 `wechat_openid`
- 推荐文本中的“更多同类产品”链接也已透传 `wechat_openid`

### 当前状态
- 图文详情页：本地 200
- 更多同类产品页：本地 200
- 推荐文本中的下单路径已与后端兼容
- 下一步应继续核查 redirect 最终跳转是否稳定到 JD 目标页


## 2026-04-16 22:25:21 redirect 双路由与 H5 链接函数修正

### 本轮修复
- 显式重写 `app/api/promotion.py`
- 确保以下两个路由同时可用：
  - `/promotion/redirect`
  - `/api/promotion/redirect`
- 修复 `wechat_recommend_h5_service.py` 中 `_detail_url()` 被误注入 `wechat_openid` 导致的 `NameError`
- 保留 `more-like-this` 链接透传 `wechat_openid`

### 当前判断
- 如果本轮本地 probe 成功返回 302，则下单主链路已恢复
- 如果仍返回 500，则下一步需要继续深入 `promotion_service / click_redirect_service / create_promotion_link_by_openid` 内部返回值


## 2026-04-16 22:30:24 架构收口说明

### 新增文档
- `docs/WECHAT_RECOMMEND_ARCHITECTURE_AUDIT_20260416.md`

### 本轮处理目标
本轮不再继续叠临时 patch，而是转为“稳定边界”方式处理：
- API 层显式持有 `SessionLocal`
- API 层统一调用 promotion service
- 将 redirect 500 的根因从“函数签名不一致”层面收口
- 对 `wechat_recommend_h5_service.py` 进行重复定义审计

### 原则
后续修改优先遵守：
1. 配置放配置文件 / 数据库
2. API 层负责 session 和 HTTP
3. service 层只做业务
4. 避免在单一大文件中继续追加 override block


## 2026-04-16 22:41:07 稳定运行时模块切换完成

### 新增稳定模块
- `app/services/wechat_recommend_runtime_service.py`

### 本轮目的
不再让线上活跃入口继续依赖 `app/services/wechat_recommend_h5_service.py` 中多轮 override 后的“最后覆盖定义”，而是切到新的稳定运行时模块。

### 已切换入口
- `app/services/message_router.py`
- `app/api/wechat_recommend_h5.py`

### 当前策略
- 旧 `wechat_recommend_h5_service.py` 暂时保留，仅作为历史参考
- 新需求和后续修复优先落在 `wechat_recommend_runtime_service.py`
- 后续再安排旧大文件清理和模块拆分收尾

## 2026-04-17 通信边界冻结（WeChat/JD）
- 公众号通信基础链路冻结：`app/api/wechat.py` -> `app/services/message_router.py` -> `app/services/wechat_service.py`
- 京东通信基础链路冻结：`app/services/jd_union_client.py` 及其直接 API 边界
- 菜单点击“今日推荐”只允许单次被动回复；不再使用客服消息二次/三次补发
- 后续业务调整只允许落在推荐运行时、规则配置、文案、H5 展示层；不得直接改动微信/JD 通信边界
- 如需新增消息形态，必须新增独立适配层，不得在回调签名、消息路由、基础发包链路上继续叠 patch
- 当前阶段以“通信稳定优先”高于“内容形态丰富度”

## 4.2 2026-04-18 商品池治理与调度 authoritative
- `jd.union.open.goods.query` 当前已恢复可用，关键修复：
  - `goodsReqDTO`
  - `sceneId=1`
  - `sortName=inOrderCount30Days`
- 夜间商品池刷新不再依赖 crontab，当前生产调度已切到：
  - `aideal-catalog-refresh.timer`
  - `aideal-catalog-refresh.service`
- 当前运行文件：
  - runner: `ops/systemd/run_catalog_refresh.sh`
  - health check: `ops/check_catalog_refresh_health.sh`
  - status file: `run/catalog_refresh_status.json`
- 当前夜间任务稳定执行：
  - `elite_refresh`
  - `keyword_refresh`
  - `inactive_cleanup`
  - `purge_cleanup`
- 当前关键词池已恢复到 4 个：
  - 洗衣液
  - 牙膏
  - 抽纸
  - 宝宝湿巾

## 6.1 当前商品池治理口径（authoritative）
- `jd_sku_id` 已改为：
  - 优先 numeric SKU
  - 历史联盟 item 风格 ID 逐步退役
- 已修复 keyword refresh 在未 flush session 内重复插入导致的唯一索引冲突
- 已新增商品合规收口：
  - 维修服务 / 本地服务 -> hard_block
  - 酒类 -> hard_block
  - 宠物滴眼液 / 宠物药 / 农药 / 杀虫剂 -> hard_block
  - 性功能暗示 / 医疗边缘商品 -> restricted 或 hard_block
- 已新增主动推荐池配置过滤：
  - 配置文件：`config/proactive_recommend_rules.json`
  - 目标：将“安全可见”与“适合主动推荐”分层
- 当前主动推荐池的实际口径为：
  - `status=active`
  - `allow_proactive_push=True`
  - `merchant_recommendable=True`
  - 命中 proactive recommend rules

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
