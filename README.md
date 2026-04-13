# AIdeal CPS

一个面向中国大陆消费者、以微信H5为入口、以京东联盟佣金为盈利方式的 AI 导购返佣系统。

## 当前对接模式
一期采用“京东联盟导购媒体”模式对接：
- JD_SITE_ID：导购媒体ID
- JD_POSITION_ID：推广位ID

说明：
- 当前项目主链路不是京东开放平台 APP 对接
- JD_APP_KEY / JD_APP_SECRET 仅作为后续真实API接入的可选预留
- 一期先完成：商品展示 -> 点击归因 -> 推广链接 -> 订单管理骨架

## Current Principles
1. 一期只做公众号 + H5，不做小程序
2. 一期只做京东联盟闭环，不做全网比价
3. 一期返现为手工返现，不做自动打款
4. AI 只做推荐增强，不做核心决策
5. 所有数据库变更必须通过 Alembic
6. 所有开发以 GitHub 仓库为准，不以聊天记录为准
7. 当前主对接方为京东联盟导购媒体，不是开放平台APP

## Development
```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

## 当前真实集成状态（2026-04）
当前分支已不再只是“预留”京东能力，而是已经打通并验证：
- jd.union.open.goods.jingfen.query
- jd.union.open.promotion.bysubunionid.get
- JD 榜单商品同步入库
- /products 作为数据库商品池查询接口
- /jd 内部接口与短链生成能力

后续主方向：
- 商家画像与风险过滤
- 公众号欢迎流与 AI 导购问答
- 自有点击归因跳转网关
