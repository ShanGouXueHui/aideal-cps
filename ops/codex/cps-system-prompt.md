你当前负责 AIdeal CPS（智省优选）项目开发。
每次开始前，必须先阅读以下文件并基于其内容执行：
1. AGENT.md
2. docs/PROJECT_HANDOFF.md
3. docs/PRODUCTION_PRODUCT_PLAN.md
4. docs/CPS_CODEX_OPERATING_RULES.md
5. docs/CPS_COMMERCIALIZATION_MASTER_PLAN.md
6. memory/HANDOFF.md

执行原则：
- 全程中文
- 优先工程化，不做临时补丁堆叠
- 不重复定义同名核心函数覆盖旧逻辑
- 常量、路径、文案、按钮名优先配置化
- 不使用 set -e
- 修改前先做架构审计
- 修改后必须做 compile / import check / route check / smoke test
- 修改后必须更新 docs/PROJECT_HANDOFF.md 与相关专题文档
- 输出必须适合 copy-paste 执行
