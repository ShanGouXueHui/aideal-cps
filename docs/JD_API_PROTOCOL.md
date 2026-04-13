# JD 联盟 API 协议说明（项目内固化）

## 1. 基础入口
https://api.jd.com/routerjson

## 2. 系统参数
- method
- app_key
- access_token (按接口是否授权决定，非必然)
- timestamp
- format=json
- v=1.0
- sign_method=md5
- sign

## 3. 业务参数
统一通过 360buy_param_json 传输。

## 4. 签名
签名字符串构造方式：
1. 排除 sign
2. 对所有参数按 key 升序
3. 拼接 key + value
4. 两端拼 appSecret
5. md5 后转大写

## 5. 已确认接口

### 5.1 jd.union.open.goods.jingfen.query
业务参数:
{
  "goodsReq": {
    "eliteId": 129,
    "pageIndex": 1,
    "pageSize": 20
  }
}

常用 eliteId:
- 22 实时热销榜
- 31 今日必推
- 33 京东秒杀
- 40 高收益榜
- 129 高佣榜单
- 153 历史最低价商品榜

### 5.2 jd.union.open.promotion.bysubunionid.get
业务参数:
{
  "promotionCodeReq": {
    "materialId": "商品链接或联盟链接",
    "siteId": "站点ID",
    "positionId": "推广位ID",
    "chainType": 2,
    "sceneId": 1
  }
}

说明:
- materialId 可传商品链接、联盟链接、活动链接等
- 推荐 chainType=2 先拿短链
- sceneId 当前先用 1


## 6. 当前代码落点
- 配置: app/core/jd_union_config.py
- 客户端: app/services/jd_union_client.py
- 单测: tests/test_jd_union_client.py
- 实网验证脚本: scripts/jd_api_smoke_test.py

## 7. 当前实现原则
- siteId / positionId 默认从 JD_PID 自动解析
- access_token 仅在 .env 存在 JD_ACCESS_TOKEN 时才带上
- jingfen.query 当前默认通过 goodsReq + 360buy_param_json 调用
- promotion.bysubunionid.get 当前默认使用:
  - chainType=2
  - sceneId=1
