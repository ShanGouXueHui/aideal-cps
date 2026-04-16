# AIdeal CPS 当前续接锚点

## 一、项目身份
- 项目：AIdeal CPS（智省优选）
- 模式：微信公众号 / H5 驱动的 AI 导购返佣系统
- 核心：京东联盟导购媒体，不做自营交易闭环
- 当前开发分支：feat/wechat-official-account

## 二、开发环境
- 开发机：新加坡服务器
- 当前开发用户：cpsdev
- 开发路径：/home/cpsdev/projects/aideal-cps
- Git SSH：已打通
- Codex 工作模式：必须先读 docs + memory，再开始开发

## 三、生产环境
- 生产服务器：8.136.28.6
- 生产用户：deploy
- 生产路径：/home/deploy/projects/aideal-cps
- systemd：aideal.service
- Web：Nginx + FastAPI + uvicorn

## 四、当前确认过的关键事实
1. 微信当前真实回调路径：/wechat/callback
2. 当前不切 AES 安全模式
3. 推荐系统必须：
   - 当前轮次内不重复
   - 池耗尽后轮转
   - 保持品类多样性
4. 下单链路必须稳定：
   - 自有 redirect
   - 再 302 到 JD short_url
5. 图文详情可用 H5
6. “更多同类产品”当前为 H5，后续升级为公众号直接返回同类 3 条
7. jingfen.query + promotion.bysubunionid.get 是当前稳定接口
8. goods.query 当前不能作为商用主链路依赖

## 五、当前工程问题
1. 推荐/H5/redirect 曾被多轮临时修补，存在覆盖式修复历史
2. 同名函数重复定义风险高
3. 常量/路径/标签一度散落硬编码
4. 必须先做架构收口，再继续商用迭代

## 六、当前优先任务
1. 做微信推荐链路架构审计
2. 收口 wechat_recommend_h5_service.py 的重复实现
3. 收口 promotion API 边界
4. 固化推荐配置、文案配置、路径配置
5. 建立开发机到生产机的稳定部署链路
6. 持续更新 docs，保证 GitHub 成为长期记忆源
