# AIdeal CPS - 当前系统状态（2026-04-16）

## 系统定位
微信服务号 + 京东联盟导购 + AI推荐系统

## 当前已完成
- 商品池（JD同步）
- 推荐逻辑（cycle_pool去重）
- H5详情页
- promotion redirect（已修复DB边界）
- 更多同类产品（H5）

## 当前问题
1. wechat callback 不稳定（导致官方号 unavailable）
2. service 文件函数重复定义（覆盖问题）
3. URL生成逻辑分散
4. 文案仍为半测试版本

## 架构目标
1. callback 只做入口
2. URL生成统一到一个模块
3. 推荐逻辑单一入口（无重复函数）
4. 文案策略可配置 / AI生成

## 下一步任务
1. 重构 wechat callback
2. 清理重复函数（wechat_recommend_h5_service）
3. 抽离 URL builder
4. 接入 Qwen 文案生成

