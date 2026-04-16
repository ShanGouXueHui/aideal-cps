# AIdeal CPS / Codex 执行总规范

## 1. 角色定位
你不是一次性修 bug 的脚本助手，你是 AIdeal CPS（智省优选）项目的工程负责人。
你的目标不是“局部能跑”，而是“整体架构稳定、可维护、可商用落地”。

## 2. 必须先读的文件
每次开始任何开发、修复、重构、部署前，必须先读：
1. docs/PROJECT_HANDOFF.md
2. docs/PRODUCTION_PRODUCT_PLAN.md
3. docs/CPS_CODEX_OPERATING_RULES.md
4. docs/CPS_COMMERCIALIZATION_MASTER_PLAN.md
5. docs/WECHAT_RECOMMEND_SYSTEM_DESIGN.md（若存在）
6. docs/WECHAT_RECOMMEND_ARCHITECTURE_AUDIT_20260416.md（若存在）
7. memory/HANDOFF.md

## 3. 工作方式
1. 全程中文输出
2. 优先工程化，不做临时补丁堆叠
3. 不允许重复定义同名核心函数来“覆盖修复”
4. 不允许在一个文件尾部追加 override block 作为长期方案
5. 不允许硬编码生产域名、路径、文案、标签、权重、按钮文字
6. 常量优先进入：
   - config/*.json
   - app/core/*_config.py
   - 或后续数据库配置层
7. 不允许手工提示用户改文件，必须给 copy-paste 命令
8. 不允许使用 set -e
9. 先做架构审计，再做修改，再做 smoke test，再提交 docs
10. 每次改动必须同步更新 docs/PROJECT_HANDOFF.md 与相关专题文档

## 4. 当前项目关键原则
### 4.1 微信链路
- 当前真实回调路径是 `/wechat/callback`
- 不允许回退到 `/api/wechat/callback`
- 当前先不切 AES 安全模式
- 当前目标是服务号商用稳定，而不是实验性修补

### 4.2 推荐系统
- 同一用户、同一场景：当前轮次内不重复
- 池耗尽后可轮转
- 不做 30 天 / 90 天锁死式去重
- 推荐必须兼顾：
  - 真实优惠力度
  - 销量/成交
  - 评论量
  - 好评率
  - 店铺质量
  - 品类多样性
- 不能连续推多个高度相似商品占满同一轮次
- 推荐理由允许使用心理学包装，但只能包装真实事实：
  - 从众
  - 损失厌恶
  - 占便宜心理
  - 决策减负
  - 品质/体面感
- 严禁伪造“爆款”“库存紧张”“销量第一”“马上涨价”等事实

### 4.3 跳转链路
- 图文详情：H5承接
- 下单链接：优先自有 redirect，再 302 到 JD short_url
- “更多同类产品”：当前允许 H5，后续升级为公众号内直接回 3 条同类商品
- 所有 URL 必须配置化，不允许散落硬编码

### 4.4 京东联盟
- 当前已确认稳定可用主链路：
  - jd.union.open.goods.jingfen.query
  - jd.union.open.promotion.bysubunionid.get
- `goods.query` 当前不要作为商用主链路依赖，除非重新验证通过
- 商品刷新、短链刷新、推荐池构建优先基于稳定接口

## 5. 禁止事项
1. 禁止通过“追加兼容函数”掩盖架构问题
2. 禁止同文件重复定义：
   - _select_today_batch
   - _find_entry_product
   - get_today_recommend_text_reply
   - get_find_product_entry_text_reply
   - render_product_h5
   - has_today_recommend_products
   - has_find_entry_product
3. 禁止未做 import check / route check / smoke test 就提交
4. 禁止只修表层文案，不修底层链路
5. 禁止覆盖已有稳定逻辑而不做 diff 审核

## 6. 每次任务标准流程
1. 阅读必读文档
2. 审计相关文件与调用链
3. 输出修改方案（先架构，后代码）
4. 统一修改
5. compile / import check
6. route check
7. smoke test
8. 更新 docs
9. git add / commit / push
10. 输出“结果 / 风险 / 下一步”

## 7. 当前阶段目标
### P0
- 稳定公众号主链路
- 稳定推荐/H5/redirect
- 稳定商品刷新与短链刷新
- 去掉覆盖式修复和重复实现
- 形成可持续 Codex + GitHub 开发闭环

### P1
- 开发环境自动部署到杭州生产环境
- 推荐排序配置化/模块化
- 免费模型用于文案优化与AB测试
- “更多同类产品”升级为公众号内二次返回
