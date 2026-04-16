from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.wechat_recommend_exposure import WechatRecommendExposure


def _cfg() -> dict[str, Any]:
    try:
        with open("config/wechat_recommend_rules.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _labels() -> dict[str, str]:
    return (_cfg().get("labels") or {}) if isinstance(_cfg().get("labels"), dict) else {}


def _url_cfg() -> dict[str, str]:
    return (_cfg().get("url") or {}) if isinstance(_cfg().get("url"), dict) else {}


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


def _active_recommend_products(db: Session) -> list[Product]:
    return (
        db.query(Product)
        .filter(Product.status == "active")
        .filter(Product.allow_proactive_push == True)
        .filter(Product.short_url.isnot(None), Product.short_url != "")
        .filter(Product.purchase_price.isnot(None))
        .filter(Product.basis_price.isnot(None))
        .filter(Product.purchase_price < Product.basis_price)
        .all()
    )


def _product_category_key(product: Product) -> str:
    return str(getattr(product, "category_name", "") or "").strip().lower()


def _product_shop_key(product: Product) -> str:
    return str(getattr(product, "shop_name", "") or "").strip().lower()


def _score(product: Product) -> float:
    purchase = float(getattr(product, "purchase_price", 0) or 0)
    basis = float(getattr(product, "basis_price", 0) or 0)
    delta = max(basis - purchase, 0.0)
    discount_rate = (delta / basis) if basis > 0 else 0.0

    sales = float(getattr(product, "sales_volume", 0) or 0)
    comments = float(getattr(product, "comment_count", 0) or 0)
    good = float(getattr(product, "good_comments_share", 0) or 0)

    sales_score = min(sales / 300.0, 1.0)
    comment_score = min(comments / 10000.0, 1.0)
    good_score = min(max((good - 90.0) / 10.0, 0.0), 1.0)

    return round(
        0.42 * discount_rate +
        0.30 * sales_score +
        0.18 * comment_score +
        0.10 * good_score,
        6,
    )


def _recent_scene_product_ids(db: Session, *, openid_hash: str, scene: str) -> set[int]:
    rows = (
        db.query(WechatRecommendExposure.product_id)
        .filter(
            WechatRecommendExposure.openid_hash == openid_hash,
            WechatRecommendExposure.scene == scene,
        )
        .all()
    )
    return {int(x[0]) for x in rows if x and x[0] is not None}


def _record_scene_exposures(db: Session, *, openid_hash: str, scene: str, products: list[Product]) -> None:
    if not products:
        return
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


def _select_today_batch(db: Session, *, wechat_openid: str) -> list[Product]:
    scene = "today_recommend"
    openid_hash = _openid_key(wechat_openid)

    products = sorted(
        _active_recommend_products(db),
        key=lambda x: (_score(x), int(getattr(x, "comment_count", 0) or 0)),
        reverse=True,
    )
    if not products:
        return []

    exposed_ids = _recent_scene_product_ids(db, openid_hash=openid_hash, scene=scene)
    fresh = [p for p in products if int(p.id) not in exposed_ids]

    # 池耗尽后立即轮转
    if len(fresh) < 3:
        fresh = list(products)

    batch: list[Product] = []
    used_ids: set[int] = set()
    used_categories: set[str] = set()
    used_shops: set[str] = set()

    # 第一轮：优先做类目/店铺多样性
    for p in fresh:
        pid = int(p.id)
        cat = _product_category_key(p)
        shop = _product_shop_key(p)
        if pid in used_ids:
            continue
        if cat and cat in used_categories:
            continue
        if shop and shop in used_shops and len(batch) < 2:
            continue
        batch.append(p)
        used_ids.add(pid)
        if cat:
            used_categories.add(cat)
        if shop:
            used_shops.add(shop)
        if len(batch) >= 3:
            break

    # 第二轮：补足到 3 个
    if len(batch) < 3:
        for p in fresh:
            pid = int(p.id)
            if pid in used_ids:
                continue
            batch.append(p)
            used_ids.add(pid)
            if len(batch) >= 3:
                break

    return batch[:3]


def _find_entry_product(db: Session, *, wechat_openid: str) -> Product | None:
    batch = _select_today_batch(db, wechat_openid=wechat_openid)
    return batch[0] if batch else None


def has_today_recommend_products(db: Session) -> bool:
    return len(_active_recommend_products(db)) > 0


def has_find_entry_product(db: Session) -> bool:
    return _find_entry_product(db, wechat_openid="compat_check_openid") is not None


def _commercial_reason(product: Product) -> str:
    delta = float(getattr(product, "basis_price", 0) or 0) - float(getattr(product, "purchase_price", 0) or 0)
    sales = int(getattr(product, "sales_volume", 0) or 0)
    comments = int(getattr(product, "comment_count", 0) or 0)
    good = float(getattr(product, "good_comments_share", 0) or 0)

    if delta >= 25 and comments >= 5000:
        return "这类单子最容易触发用户的“占便宜”心理：价差已经拉开，评论沉淀又足，点进去就能快速判断要不要锁单。"
    if sales >= 200:
        return "这类商品更容易承接“从众+损失厌恶”心理：已经有不少人下单，继续观望的心理成本会更高。"
    if good >= 98 and comments >= 2000:
        return "它更适合“省决策成本”场景：口碑和评论基数都比较稳，不用再花太多时间自己反复筛选。"
    return "它的核心不是噱头，而是帮用户减少比较动作：先看详情，再按实时页面决定是否下单，会更省时间。"


def _format_price_line(product: Product) -> str:
    try:
        from app.services.recommend_price_copy_service import format_recommend_price_text
        txt = format_recommend_price_text(product)
        if txt:
            return txt
    except Exception:
        pass

    purchase = getattr(product, "purchase_price", None)
    basis = getattr(product, "basis_price", None)
    if purchase is not None and basis is not None:
        try:
            delta = float(basis) - float(purchase)
            return f"优惠价￥{float(purchase):.2f}｜京东官网价￥{float(basis):.2f}｜立省￥{delta:.2f}"
        except Exception:
            pass
    return "价格以下单页实时信息为准"


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
        lines.extend([
            f"【{idx}】{getattr(product, 'title', '')}",
            f"💰 到手参考：{_format_price_line(product)}",
            f"✨ 推荐理由：{_commercial_reason(product)}",
            f"📄 {LABEL_DETAIL}：{_detail_url(product, scene='today_recommend', slot=idx, wechat_openid=wechat_openid)}",
            f"🛒 {LABEL_BUY}：{_promotion_url(product, wechat_openid=wechat_openid, scene='today_recommend', slot=idx)}",
            f"🔎 {LABEL_MORE}：{_more_like_this_url(product, scene='today_recommend', slot=idx, wechat_openid=wechat_openid)}",
            "",
        ])
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

    return "\n".join([
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
    ]).strip()


def render_product_h5(product: Product, *, scene: str = "", slot: str = "", wechat_openid: str = "") -> str:
    title = html.escape(str(getattr(product, "title", "") or "商品详情"))
    shop_name = html.escape(str(getattr(product, "shop_name", "") or ""))
    category_name = html.escape(str(getattr(product, "category_name", "") or ""))
    image_url = html.escape(str(getattr(product, "image_url", "") or ""))
    price_text = html.escape(_format_price_line(product))
    reason_text = html.escape(_commercial_reason(product))

    scene_val = scene or "today_recommend"
    slot_val = int(slot or 1)

    detail_url = _detail_url(product, scene=scene_val, slot=slot_val, wechat_openid=wechat_openid)
    buy_url = _promotion_url(product, wechat_openid=wechat_openid or "h5_detail_openid", scene=scene_val, slot=slot_val)
    more_url = _more_like_this_url(product, scene=scene_val, slot=slot_val, wechat_openid=wechat_openid)

    image_block = ""
    if image_url:
        image_block = f'<img src="{image_url}" alt="{title}" style="width:100%;border-radius:18px;display:block;background:#fff;" />'

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
      <title>{title}</title>
      <style>
        body{{margin:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f172a;}}
        .wrap{{max-width:760px;margin:0 auto;padding:18px 16px 40px;}}
        .card{{background:#fff;border-radius:20px;padding:18px;box-shadow:0 6px 24px rgba(15,23,42,.06);}}
        .title{{font-size:22px;font-weight:800;line-height:1.5;margin:14px 0 0;}}
        .meta{{margin-top:10px;color:#64748b;line-height:1.8;font-size:14px;}}
        .price{{margin-top:14px;padding:14px;border-radius:14px;background:#fff7ed;color:#9a3412;line-height:1.8;font-weight:700;}}
        .reason{{margin-top:14px;padding:14px;border-radius:14px;background:#f8fafc;line-height:1.8;color:#334155;}}
        .actions{{margin-top:18px;display:flex;gap:10px;flex-wrap:wrap;}}
        .btn{{display:inline-block;padding:12px 16px;border-radius:12px;text-decoration:none;font-weight:700;}}
        .btn-detail{{background:#eef2ff;color:#3730a3;}}
        .btn-buy{{background:#dcfce7;color:#166534;}}
        .btn-more{{background:#fff7ed;color:#c2410c;}}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="card">
          {image_block}
          <div class="title">{title}</div>
          <div class="meta">店铺：{shop_name or "暂无"}<br/>分类：{category_name or "暂无"}</div>
          <div class="price">💰 到手参考：{price_text}</div>
          <div class="reason">✨ 推荐理由：{reason_text}</div>
          <div class="actions">
            <a class="btn btn-detail" href="{detail_url}">图文详情</a>
            <a class="btn btn-buy" href="{buy_url}">下单链接</a>
            <a class="btn btn-more" href="{more_url}">更多同类产品</a>
          </div>
        </div>
      </div>
    </body>
    </html>
    """
