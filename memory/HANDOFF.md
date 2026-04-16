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
1. 微信当前真实回调路径：/wechat/callback
2. 当前不切 AES 安全模式
3. 推荐系统必须：
   - 当前轮次内不重复
   - 池耗尽后轮转
   - 保持品类多样性
4. 下单链路必须稳定：
   - 自有 redirect
   - 再 302 到 JD short_url
5. 图文详情可用 H5
6. “更多同类产品”当前为 H5，后续升级为公众号直接返回同类 3 条
7. jingfen.query + promotion.bysubunionid.get 是当前稳定接口
8. goods.query 当前不能作为商用主链路依赖

## 五、当前工程问题
1. 推荐/H5/redirect 曾被多轮临时修补，存在覆盖式修复历史
2. 同名函数重复定义风险高
3. 常量/路径/标签一度散落硬编码
4. 必须先做架构收口，再继续商用迭代

## 六、当前优先任务
1. 做微信推荐链路架构审计
2. 收口 wechat_recommend_h5_service.py 的重复实现
3. 收口 promotion API 边界
4. 固化推荐配置、文案配置、路径配置
5. 建立开发机到生产机的稳定部署链路
6. 持续更新 docs，保证 GitHub 成为长期记忆源

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
