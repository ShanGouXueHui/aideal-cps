# CPS 生产发布流程（骨架）

## 1. 原则
- 开发机先验证
- 先 rsync preview，再正式同步
- 生产机先备份，再 compile，再 restart，再 probe
- 不直接在生产机长期裸改

## 2. 当前建议顺序
1. 新加坡开发机完成修改
2. git commit + push
3. rsync preview
4. rsync 正式同步
5. 杭州机执行 remote_apply.sh
6. 验证：
   - /wechat/callback
   - /api/promotion/redirect
   - /api/h5/recommend/{product_id}
   - 服务号菜单点击链路
7. 更新 docs/PROJECT_HANDOFF.md

## 3. 当前未完成
- 生产机 SSH 免密
- 开发机到生产机固定 deploy 用户信任
- VPN / WireGuard
- 自动化一键部署

## 2026-04-17 通信边界冻结（WeChat/JD）
- 公众号通信基础链路冻结：`app/api/wechat.py` -> `app/services/message_router.py` -> `app/services/wechat_service.py`
- 京东通信基础链路冻结：`app/services/jd_union_client.py` 及其直接 API 边界
- 菜单点击“今日推荐”只允许单次被动回复；不再使用客服消息二次/三次补发
- 后续业务调整只允许落在推荐运行时、规则配置、文案、H5 展示层；不得直接改动微信/JD 通信边界
- 如需新增消息形态，必须新增独立适配层，不得在回调签名、消息路由、基础发包链路上继续叠 patch
- 当前阶段以“通信稳定优先”高于“内容形态丰富度”
