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
