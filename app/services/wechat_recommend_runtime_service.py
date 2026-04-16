from __future__ import annotations

import hashlib
import html
import json
import re
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.wechat_recommend_exposure import WechatRecommendExposure


def _cfg() -> dict[str, Any]:
    try:
        with open("config/wechat_recommend_rules.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _labels() -> dict[str, str]:
    val = _cfg().get("labels") or {}
    return val if isinstance(val, dict) else {}


def _url_cfg() -> dict[str, str]:
    val = _cfg().get("url") or {}
    return val if isinstance(val, dict) else {}


def _text_label(key: str, default: str) -> str:
    return str(_labels().get(key) or default)


LABEL_DETAIL = _text_label("detail", "图文详情")
LABEL_BUY = _text_label("buy", "下单链接")
LABEL_MORE = _text_label("more_like_this", "更多同类产品")


def _public_base_url() -> str:
    try:
        from app.core.wechat_recommend_config import PUBLIC_BASE_URL

        if PUBLIC_BASE_URL:
            return str(PUBLIC_BASE_URL).rstrip("/")
    except Exception:
        pass
    return "https://aidealfy.kindafeelfy.cn"


def _openid_key(openid: str) -> str:
    return hashlib.sha1(str(openid).encode("utf-8")).hexdigest()[:24]


def _promotion_url(product: Product, *, wechat_openid: str, scene: str, slot: int) -> str:
    tpl = str(
        _url_cfg().get("promotion_redirect_path_template")
        or "/api/promotion/redirect?wechat_openid={wechat_openid}&product_id={product_id}&scene={scene}&slot={slot}"
    )
    return _public_base_url() + tpl.format(
        wechat_openid=quote(str(wechat_openid), safe=""),
        product_id=int(product.id),
        scene=quote(str(scene), safe=""),
        slot=int(slot),
    )


def _detail_url(product: Product, *, scene: str, slot: int, wechat_openid: str = "") -> str:
    tpl = str(
        _url_cfg().get("recommend_h5_path_template")
        or "/api/h5/recommend/{product_id}?scene={scene}&slot={slot}"
    )
    base = _public_base_url() + tpl.format(
        product_id=int(product.id),
        scene=quote(str(scene), safe=""),
        slot=int(slot),
    )
    if wechat_openid:
        joiner = "&" if "?" in base else "?"
        base = f"{base}{joiner}wechat_openid={quote(str(wechat_openid), safe='')}"
    return base


def _more_like_this_url(product: Product, *, scene: str, slot: int, wechat_openid: str = "") -> str:
    tpl = str(
        _url_cfg().get("more_like_this_path_template")
        or "/api/h5/recommend/more-like-this?product_id={product_id}&scene={scene}&slot={slot}"
    )
    base = _public_base_url() + tpl.format(
        product_id=int(product.id),
        scene=quote(str(scene), safe=""),
        slot=int(slot),
    )
    if wechat_openid:
        joiner = "&" if "?" in base else "?"
        base = f"{base}{joiner}wechat_openid={quote(str(wechat_openid), safe='')}"
    return base


def get_product_by_id(db: Session, product_id: int) -> Product | None:
    return db.query(Product).filter(Product.id == int(product_id)).first()


def _to_float(v: Any) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def _to_int(v: Any) -> int:
    try:
        if v is None or v == "":
            return 0
        return int(v)
    except Exception:
        return 0


def _effective_price(product: Product) -> float:
    price = _to_float(getattr(product, "price", None))
    coupon_price = _to_float(getattr(product, "coupon_price", None))
    if coupon_price > 0 and (price <= 0 or coupon_price <= price):
        return coupon_price
    return price


def _saved_amount(product: Product) -> float:
    price = _to_float(getattr(product, "price", None))
    effective = _effective_price(product)
    if price > 0 and effective > 0 and effective < price:
        return round(price - effective, 2)
    return 0.0


def _saved_rate(product: Product) -> float:
    price = _to_float(getattr(product, "price", None))
    saved = _saved_amount(product)
    if price > 0:
        return saved / price
    return 0.0


def _shop_name(product: Product) -> str:
    return str(getattr(product, "shop_name", "") or "").strip()


def _category_key(product: Product) -> str:
    return str(getattr(product, "category_name", "") or "").strip().lower()


def _shop_key(product: Product) -> str:
    shop = _shop_name(product).lower()
    for s in ("京东自营旗舰店", "官方旗舰店", "自营旗舰店", "旗舰店", "官方店", "品牌店", "专卖店", "专营店"):
        shop = shop.replace(s, "")
    return shop.strip()


def _title_key(product: Product) -> str:
    title = str(getattr(product, "title", "") or "").lower()
    tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", title)
    if not tokens:
        return str(getattr(product, "id", "") or "")
    return "".join(tokens[:2])[:32]


def _is_flagship_or_self_operated(product: Product) -> bool:
    shop = _shop_name(product)
    return any(x in shop for x in ("京东自营", "旗舰店", "官方店", "品牌店"))


def _active_recommend_products(db: Session) -> list[Product]:
    q = (
        db.query(Product)
        .filter(Product.status == "active")
        .filter(Product.short_url.isnot(None), Product.short_url != "")
    )
    merchant_recommendable = getattr(Product, "merchant_recommendable", None)
    if merchant_recommendable is not None:
        q = q.filter(merchant_recommendable == True)
    return q.all()


def _score(product: Product) -> float:
    saved_rate = _saved_rate(product)
    sales = _to_float(getattr(product, "sales_volume", None))
    merchant = _to_float(getattr(product, "merchant_health_score", None))
    flagship = 1.0 if _is_flagship_or_self_operated(product) else 0.0
    sales_score = min(sales / 300.0, 1.0)
    merchant_score = min(max((merchant - 70.0) / 30.0, 0.0), 1.0)
    return round(
        0.45 * saved_rate
        + 0.25 * sales_score
        + 0.20 * merchant_score
        + 0.10 * flagship,
        6,
    )


def _recent_scene_product_ids(db: Session, *, openid_hash: str, scene: str) -> set[int]:
    try:
        rows = (
            db.query(WechatRecommendExposure.product_id)
            .filter(
                WechatRecommendExposure.openid_hash == openid_hash,
                WechatRecommendExposure.scene == scene,
            )
            .all()
        )
        return {int(x[0]) for x in rows if x and x[0] is not None}
    except Exception:
        return set()


def _reset_scene_exposures(db: Session, *, openid_hash: str, scene: str) -> None:
    try:
        (
            db.query(WechatRecommendExposure)
            .filter(
                WechatRecommendExposure.openid_hash == openid_hash,
                WechatRecommendExposure.scene == scene,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
    except Exception:
        db.rollback()


def _record_scene_exposures(db: Session, *, openid_hash: str, scene: str, products: list[Product]) -> None:
    if not products:
        return
    try:
        rows = [
            WechatRecommendExposure(
                openid_hash=openid_hash,
                scene=scene,
                product_id=int(product.id),
            )
            for product in products
        ]
        db.add_all(rows)
        db.commit()
    except Exception:
        db.rollback()


def _pick_diverse(products: list[Product], limit: int) -> list[Product]:
    picked: list[Product] = []
    used_ids: set[int] = set()
    used_categories: set[str] = set()
    used_shops: set[str] = set()
    used_titles: set[str] = set()

    for p in products:
        pid = int(p.id)
        cat = _category_key(p)
        shop = _shop_key(p)
        titlek = _title_key(p)

        if pid in used_ids:
            continue
        if cat and cat in used_categories:
            continue
        if shop and shop in used_shops:
            continue
        if titlek and titlek in used_titles:
            continue

        picked.append(p)
        used_ids.add(pid)
        if cat:
            used_categories.add(cat)
        if shop:
            used_shops.add(shop)
        if titlek:
            used_titles.add(titlek)

        if len(picked) >= limit:
            return picked

    for p in products:
        pid = int(p.id)
        if pid in used_ids:
            continue
        picked.append(p)
        used_ids.add(pid)
        if len(picked) >= limit:
            return picked

    return picked


def _sorted_candidates(db: Session) -> list[Product]:
    return sorted(
        _active_recommend_products(db),
        key=lambda x: (
            _score(x),
            _to_int(getattr(x, "sales_volume", None)),
            int(getattr(x, "id", 0) or 0),
        ),
        reverse=True,
    )


def _select_scene_batch(db: Session, *, wechat_openid: str, scene: str, limit: int) -> list[Product]:
    products = _sorted_candidates(db)
    if not products:
        return []

    openid_hash = _openid_key(wechat_openid)
    exposed_ids = _recent_scene_product_ids(db, openid_hash=openid_hash, scene=scene)
    fresh = [p for p in products if int(p.id) not in exposed_ids]

    if len(fresh) < limit:
        _reset_scene_exposures(db, openid_hash=openid_hash, scene=scene)
        fresh = list(products)

    batch = _pick_diverse(fresh, limit)
    return batch[:limit]


def _select_today_batch(db: Session, *, wechat_openid: str) -> list[Product]:
    return _select_scene_batch(
        db,
        wechat_openid=wechat_openid,
        scene="today_recommend",
        limit=3,
    )


def _find_entry_product(db: Session, *, wechat_openid: str) -> Product | None:
    rows = _select_scene_batch(
        db,
        wechat_openid=wechat_openid,
        scene="find_product_entry",
        limit=1,
    )
    return rows[0] if rows else None


def has_today_recommend_products(db: Session) -> bool:
    return len(_active_recommend_products(db)) > 0


def has_find_entry_product(db: Session) -> bool:
    return _find_entry_product(db, wechat_openid="compat_check_openid") is not None


def _format_price_line(product: Product) -> str:
    price = _to_float(getattr(product, "price", None))
    effective = _effective_price(product)
    saved = _saved_amount(product)

    if price > 0 and effective > 0 and effective < price:
        return f"优惠价￥{effective:.2f}｜京东官网价￥{price:.2f}｜立省￥{saved:.2f}"
    if effective > 0:
        return f"到手参考￥{effective:.2f}｜以下单页实时信息为准"
    if price > 0:
        return f"价格￥{price:.2f}｜以下单页实时信息为准"
    return "价格以下单页实时信息为准"


def _commercial_reason(product: Product) -> str:
    saved = _saved_amount(product)
    saved_rate = _saved_rate(product)
    sales = _to_int(getattr(product, "sales_volume", None))
    merchant = _to_float(getattr(product, "merchant_health_score", None))
    flagship = _is_flagship_or_self_operated(product)

    if saved >= 20 or saved_rate >= 0.30:
        if sales >= 100:
            return "这类单子更容易触发“占便宜+损失厌恶”：当前价差已经拉开，销量也不弱，继续观望的机会成本更高。"
        return "这类单子更容易触发“占便宜”心理：当前价差已经拉开，先点进去看实时页面，判断成本最低。"

    if sales >= 200:
        return "这类商品更容易承接“从众+损失厌恶”心理：已经有不少人下单，继续拖延的心理成本会更高。"

    if flagship or merchant >= 85:
        return "这类商品更适合“品质/省心”场景：店铺确定性更高，先看详情再下单，决策负担更低。"

    return "它的核心不是噱头，而是帮用户减少比较动作：先看详情，再按实时页面决定是否下单，会更省时间。"


def get_today_recommend_text_reply(db: Session, wechat_openid: str) -> str | None:
    batch = _select_today_batch(db, wechat_openid=wechat_openid)
    if not batch:
        return "当前可推荐商品还在整理中，稍后再试。"

    _record_scene_exposures(
        db,
        openid_hash=_openid_key(wechat_openid),
        scene="today_recommend",
        products=batch,
    )

    lines = ["🔥 今日推荐 3 个，可直接购买：", ""]
    for idx, product in enumerate(batch, 1):
        lines.extend(
            [
                f"{getattr(product, 'title', '')}",
                f"💰 到手参考：{_format_price_line(product)}",
                f"✨ 推荐理由：{_commercial_reason(product)}",
                f"📄 {LABEL_DETAIL}：{_detail_url(product, scene='today_recommend', slot=idx, wechat_openid=wechat_openid)}",
                f"🛒 {LABEL_BUY}：{_promotion_url(product, wechat_openid=wechat_openid, scene='today_recommend', slot=idx)}",
                f"🔎 {LABEL_MORE}：{_more_like_this_url(product, scene='today_recommend', slot=idx, wechat_openid=wechat_openid)}",
                "",
            ]
        )
    lines.append("👉 再点一次“今日推荐”，继续下一组 3 个。")
    return "\n".join(lines).strip()


def get_find_product_entry_text_reply(db: Session, wechat_openid: str) -> str | None:
    product = _find_entry_product(db, wechat_openid=wechat_openid)
    if not product:
        return "👉 也可以直接回复你想买的商品，比如：卫生纸、洗衣液、宝宝湿巾。"

    _record_scene_exposures(
        db,
        openid_hash=_openid_key(wechat_openid),
        scene="find_product_entry",
        products=[product],
    )

    return "\n".join(
        [
            "🔥 先给你放 1 个当前更稳的入口商品：",
            "",
            f"【1】{getattr(product, 'title', '')}",
            f"💰 到手参考：{_format_price_line(product)}",
            f"✨ 推荐理由：{_commercial_reason(product)}",
            f"📄 {LABEL_DETAIL}：{_detail_url(product, scene='find_product_entry', slot=1, wechat_openid=wechat_openid)}",
            f"🛒 {LABEL_BUY}：{_promotion_url(product, wechat_openid=wechat_openid, scene='find_product_entry', slot=1)}",
            f"🔎 {LABEL_MORE}：{_more_like_this_url(product, scene='find_product_entry', slot=1, wechat_openid=wechat_openid)}",
            "",
            "👉 也可以直接回复你想买的商品，比如：卫生纸、洗衣液、宝宝湿巾。",
        ]
    ).strip()


def _html_shell(title: str, body: str) -> str:
    safe_title = html.escape(title)
    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>{safe_title}</title>
  <style>
    body{{margin:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f172a;}}
    .wrap{{max-width:760px;margin:0 auto;padding:18px 16px 40px;}}
    .card{{background:#fff;border-radius:20px;padding:18px;box-shadow:0 6px 24px rgba(15,23,42,.06);margin-bottom:16px;}}
    .title{{font-size:22px;font-weight:800;line-height:1.5;margin:0;}}
    .meta{{margin-top:10px;color:#64748b;line-height:1.8;font-size:14px;}}
    .price{{margin-top:14px;padding:14px;border-radius:14px;background:#fff7ed;color:#9a3412;line-height:1.8;font-weight:700;}}
    .reason{{margin-top:14px;color:#334155;line-height:1.8;}}
    .hero{{width:100%;border-radius:16px;background:#fff;object-fit:cover;display:block;}}
    .actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;}}
    .btn{{display:inline-block;padding:12px 16px;border-radius:12px;text-decoration:none;font-weight:700;}}
    .btn-primary{{background:#0f172a;color:#fff;}}
    .btn-secondary{{background:#e2e8f0;color:#0f172a;}}
  </style>
</head>
<body>
  <div class="wrap">
    {body}
  </div>
</body>
</html>
""".strip()


def render_product_h5(product: Product, *, scene: str = "", slot: str = "", wechat_openid: str = "") -> str:
    title = html.escape(str(getattr(product, "title", "") or "商品详情"))
    shop_name = html.escape(_shop_name(product) or "店铺信息以京东页面为准")
    category_name = html.escape(str(getattr(product, "category_name", "") or ""))
    image_url = html.escape(str(getattr(product, "image_url", "") or ""))
    price_text = html.escape(_format_price_line(product))
    reason_text = html.escape(_commercial_reason(product))
    scene_val = scene or "today_recommend"
    slot_val = int(slot or 1)

    image_block = ""
    if image_url:
        image_block = f'<img class="hero" src="{image_url}" alt="{title}" />'

    body = f"""
    <div class="card">
      {image_block}
      <div class="title" style="margin-top:14px;">{title}</div>
      <div class="meta">店铺：{shop_name}<br/>分类：{category_name or "未分类"}</div>
      <div class="price">💰 {price_text}</div>
      <div class="reason">✨ 推荐理由：{reason_text}</div>
      <div class="actions">
        <a class="btn btn-secondary" href="{_more_like_this_url(product, scene=scene_val, slot=slot_val, wechat_openid=wechat_openid)}">{html.escape(LABEL_MORE)}</a>
        <a class="btn btn-primary" href="{_promotion_url(product, wechat_openid=wechat_openid or 'h5_detail_openid', scene=scene_val, slot=slot_val)}">{html.escape(LABEL_BUY)}</a>
      </div>
    </div>
    """.strip()

    return _html_shell(title, body)


def render_more_like_this_h5(
    db: Session,
    *,
    product_id: int,
    scene: str = "",
    slot: str = "",
    wechat_openid: str = "",
) -> str:
    base_product = get_product_by_id(db, int(product_id))
    if not base_product:
        return _html_shell("商品不存在", '<div class="card"><div class="title">商品不存在</div></div>')

    rows = _active_recommend_products(db)
    rows = [x for x in rows if int(x.id) != int(product_id)]

    base_cat = _category_key(base_product)
    base_shop = _shop_key(base_product)

    if base_cat:
        same_bucket = [x for x in rows if _category_key(x) == base_cat]
        if same_bucket:
            rows = same_bucket
    elif base_shop:
        same_bucket = [x for x in rows if _shop_key(x) == base_shop]
        if same_bucket:
            rows = same_bucket

    rows = sorted(
        rows,
        key=lambda x: (
            _score(x),
            _to_int(getattr(x, "sales_volume", None)),
            int(getattr(x, "id", 0) or 0),
        ),
        reverse=True,
    )
    rows = _pick_diverse(rows, 3)

    cards: list[str] = []
    scene_val = scene or "more_like_this"
    slot_base = _to_int(slot or 0)

    for idx, x in enumerate(rows, 1):
        title = html.escape(str(getattr(x, "title", "") or ""))
        price_text = html.escape(_format_price_line(x))
        reason_text = html.escape(_commercial_reason(x))
        detail_link = _detail_url(
            x,
            scene=scene_val,
            slot=slot_base + idx,
            wechat_openid=wechat_openid,
        )
        buy_link = _promotion_url(
            x,
            wechat_openid=wechat_openid or "more_like_this_openid",
            scene=scene_val,
            slot=slot_base + idx,
        )
        cards.append(
            f"""
            <div class="card">
              <div class="title">{idx}. {title}</div>
              <div class="price">💰 {price_text}</div>
              <div class="reason">✨ 推荐理由：{reason_text}</div>
              <div class="actions">
                <a class="btn btn-secondary" href="{detail_link}">{html.escape(LABEL_DETAIL)}</a>
                <a class="btn btn-primary" href="{buy_link}">{html.escape(LABEL_BUY)}</a>
              </div>
            </div>
            """.strip()
        )

    intro = """
    <div class="card">
      <div class="title">更多同类产品</div>
      <div class="meta">基于当前商品分类/店铺相近度，补充 3 个可继续对比的同类商品。</div>
    </div>
    """.strip()

    body = intro + "\n" + ("\n".join(cards) if cards else '<div class="card"><div class="title">当前还没有更多同类商品。</div></div>')
    return _html_shell("更多同类产品", body)
