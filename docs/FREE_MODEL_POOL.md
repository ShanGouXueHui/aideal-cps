# 免费模型池机制设计

## 目标
构建一个不会限制终端用户 token 使用的“免费模型池”：
- 自动刷新 provider 列表
- 自动排序
- 自动淘汰连续失败 provider
- 冷却后自动恢复
- 可与业务主链路解耦

## 一期设计
- Provider 状态持久化到本地 JSON 文件
- 每个 provider 维护：
  - provider_id
  - model_name
  - base_url
  - api_key_env
  - enabled
  - priority
  - consecutive_failures
  - total_success
  - total_failures
  - avg_latency_ms
  - last_error
  - disabled_until
  - last_checked_at
- 选择策略：
  1. 过滤 disabled / cooldown 中 provider
  2. priority 高优先
  3. consecutive_failures 少优先
  4. avg_latency_ms 低优先
- 淘汰策略：
  - 连续失败达到阈值时进入冷却
  - 冷却时间到后自动恢复候选
- 后续再接：
  - OpenRouter 免费模型
  - 其他免费 provider
  - AI 推荐服务调用层
