# CPS Codex 执行规则

## 1. 目的
避免反复覆盖、重复修补、忘记上下文、把临时方案带进商用主干。

## 2. 必须遵守
- 每次任务前先读：
  - docs/PROJECT_HANDOFF.md
  - docs/PRODUCTION_PRODUCT_PLAN.md
  - docs/CPS_CODEX_OPERATING_RULES.md
  - docs/CPS_COMMERCIALIZATION_MASTER_PLAN.md
  - memory/HANDOFF.md
- 每次修改后必须做：
  - compile
  - import check
  - route check
  - smoke test
  - docs update
- 每次提交必须写清：
  - 修了什么
  - 为什么修
  - 风险是什么
  - 下一步是什么

## 3. 代码规范
- 配置优先，避免硬编码
- 单一职责，避免一个 service 既做配置又做拼装又做路由兼容
- 禁止通过文件尾部 override block 长期修复
- 禁止重复定义同名函数进行覆盖
- 禁止为了兼容旧逻辑把错误设计永久保留在主链路
- 可迁移的临时兼容层，必须写清理计划

## 4. 发布规范
- 开发机先完成验证
- 通过 GitHub 分支提交
- 再走生产部署
- 不允许直接在生产机裸改作为长期方案

## 2026-04-17 transport freeze boundary

Codex/后续协作必须遵守：

- 不直接重构或重写 `app/api/wechat.py`
- 不直接重构或重写 `app/services/message_router.py`
- 不直接重构或重写 `app/services/wechat_service.py`
- 不直接改坏 JD 通信协议层
- 业务改动默认落在独立 service / renderer / builder，不得把业务逻辑塞回通信层

## 2026-04-17 通信边界冻结（WeChat/JD）
- 公众号通信基础链路冻结：`app/api/wechat.py` -> `app/services/message_router.py` -> `app/services/wechat_service.py`
- 京东通信基础链路冻结：`app/services/jd_union_client.py` 及其直接 API 边界
- 菜单点击“今日推荐”只允许单次被动回复；不再使用客服消息二次/三次补发
- 后续业务调整只允许落在推荐运行时、规则配置、文案、H5 展示层；不得直接改动微信/JD 通信边界
- 如需新增消息形态，必须新增独立适配层，不得在回调签名、消息路由、基础发包链路上继续叠 patch
- 当前阶段以“通信稳定优先”高于“内容形态丰富度”
