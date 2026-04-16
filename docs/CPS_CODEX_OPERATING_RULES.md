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
