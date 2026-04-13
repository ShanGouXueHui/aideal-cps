# HANDOFF

读取顺序：
1. docs/PROJECT_HANDOFF.md
2. docs/JD_API_PROTOCOL.md
3. docs/FREE_MODEL_POOL.md

当前最关键结论：
- JD 联盟 1.0 API 不能再按 apiName + 平铺参数调用
- 必须按 method + 360buy_param_json + sign_method + sign 调用
- jingfen.query 已有成功样例
- promotion.bysubunionid.get 已有文档结构，但权限和实调仍需最终打通
- 本仓库后续必须持续沉淀 handoff 文档，避免长上下文丢失
