from __future__ import annotations

import hashlib
import html
import json
from functools import lru_cache
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.wechat_recommend_exposure import WechatRecommendExposure
from app.services.product_compliance_service import apply_product_visibility_filter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
RUN_DIR = PROJECT_ROOT / "run"


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _proactive_recommend_cfg() -> dict[str, Any]:
    cfg = _load_json_file(CONFIG_DIR / "proactive_recommend_rules.json")
    if not cfg.get("dynamic_whitelist_enabled", True):
        return cfg

    path_value = str(cfg.get("dynamic_include_category_keywords_path") or "run/proactive_recommend_whitelist.json").strip()
    dynamic_path = Path(path_value)
    if not dynamic_path.is_absolute():
        dynamic_path = PROJECT_ROOT / dynamic_path

    dynamic = _load_json_file(dynamic_path)
    categories = dynamic.get("include_category_keywords") or dynamic.get("derived_categories")
    if isinstance(categories, list) and categories:
        merged = dict(cfg)
        merged["include_category_keywords"] = [str(x).strip() for x in categories if str(x).strip()]
        blocked_ids = dynamic.get("blocked_product_ids") or []
        if isinstance(blocked_ids, list):
            merged["blocked_product_ids"] = [int(x) for x in blocked_ids if str(x).strip().isdigit()]
        merged["dynamic_whitelist_meta"] = {
            "path": str(dynamic_path),
            "generated_at": dynamic.get("generated_at"),
            "candidate_count": dynamic.get("candidate_count"),
            "derived_category_count": dynamic.get("derived_category_count"),
        }
        return merged

    return cfg


@lru_cache(maxsize=1)
def _recommend_copy_cfg() -> dict[str, Any]:
    try:
        path = CONFIG_DIR / "recommend_copy_rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _copy_text(group: str, key: str, default: str) -> str:
    cfg = _recommend_copy_cfg()
    section = cfg.get(group) or {}
    if isinstance(section, dict):
        value = str(section.get(key) or "").strip()
        if value:
            return value
    return default


def _cfg_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip().lower() for x in value if str(x).strip()]


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any_keyword(text: str, keywords: list[str]) -> bool:
    return any(k and k in text for k in keywords)


def _is_commercial_proactive_candidate(product: Product) -> bool:
    cfg = _proactive_recommend_cfg()
    if not cfg.get("enabled", True):
        return True

    blocked_product_ids = cfg.get("blocked_product_ids") or []
    try:
        if int(getattr(product, "id", 0) or 0) in {int(x) for x in blocked_product_ids}:
            return False
    except Exception:
        pass

    title_text = _norm_text(getattr(product, "title", None))
    category_text = _norm_text(getattr(product, "category_name", None))
    shop_text = _norm_text(getattr(product, "shop_name", None))

    include_category_keywords = _cfg_text_list(cfg.get("include_category_keywords"))
    exclude_category_keywords = _cfg_text_list(cfg.get("exclude_category_keywords"))
    exclude_title_keywords = _cfg_text_list(cfg.get("exclude_title_keywords"))
    exclude_shop_keywords = _cfg_text_list(cfg.get("exclude_shop_keywords"))

    if exclude_category_keywords and _contains_any_keyword(category_text, exclude_category_keywords):
        return False
    if exclude_title_keywords and _contains_any_keyword(title_text, exclude_title_keywords):
        return False
    if exclude_shop_keywords and _contains_any_keyword(shop_text, exclude_shop_keywords):
        return False

    if include_category_keywords and not _contains_any_keyword(category_text, include_category_keywords):
        return False

    min_effective_price = _to_float(cfg.get("min_effective_price", cfg.get("min_coupon_price", 0)))
    max_effective_price = _to_float(cfg.get("max_effective_price", 0))
    min_estimated_commission = _to_float(cfg.get("min_estimated_commission", 0))
    min_sales_volume = _to_int(cfg.get("min_sales_volume", 0))

    effective_price = _effective_price(product)
    estimated_commission = _to_float(getattr(product, "estimated_commission", None))
    sales_volume = _to_int(getattr(product, "sales_volume", None))

    if min_effective_price > 0 and (effective_price <= 0 or effective_price < min_effective_price):
        return False
    if max_effective_price > 0 and effective_price > max_effective_price:
        return False
    if min_estimated_commission > 0 and estimated_commission < min_estimated_commission:
        return False
    if min_sales_volume > 0 and sales_volume < min_sales_volume:
        return False

    return True


def _filter_commercial_proactive_pool(products: list[Product]) -> list[Product]:
    cfg = _proactive_recommend_cfg()
    if not cfg.get("enabled", True):
        return products

    filtered = [p for p in products if _is_commercial_proactive_candidate(p)]
    if cfg.get("fallback_to_base_pool", False):
        min_candidates = int(cfg.get("fallback_min_candidates", 0) or 0)
        if len(filtered) < min_candidates:
            return products
    return filtered


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
    return "https://aidealfy.cn"


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
    q = apply_product_visibility_filter(
        q,
        require_proactive_push=True,
    )
    merchant_recommendable = getattr(Product, "merchant_recommendable", None)
    if merchant_recommendable is not None:
        q = q.filter(merchant_recommendable == True)
    rows = q.all()
    return _filter_commercial_proactive_pool(rows)


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

    if saved >= 20 or saved_rate >= 0.25:
        if sales >= 100:
            return "价差已经拉开，也有人在买，属于更适合先点开实时页、再决定下不下单的商品。"
        return "这类商品更适合先冲着省钱去看实时页：先确认到手价，再决定是否下单，决策成本最低。"

    if sales >= 1000:
        return "这类商品更吃“从众+省心”心理：销量基础更稳，不想反复比价时更适合先看实时页。"

    if flagship or merchant >= 85:
        return "店铺确定性更高，适合想省心下单时优先看一眼，先确认当前到手门槛再决定。"

    return "信息已经比较完整，适合先看实时页面，再决定是否下单，不必先花时间做无效比较。"



def _wechat_safe_title(product: Product, limit: int = 22) -> str:
    raw = ((getattr(product, "title", "") or "").strip()).replace("\n", " ")
    if len(raw) <= limit:
        return raw
    return raw[: max(1, limit - 1)] + "…"


def _compact_price_line(product: Product, ultra: bool = False) -> str:
    line = _format_price_line(product)
    line = line.replace("💰 到手参考：", "💰 ")
    line = line.replace("优惠价", "券后")
    line = line.replace("京东官网价", "原价")
    line = line.replace("｜立省", "｜省")
    if ultra:
        line = line.replace("｜原价", " / 原价")
    return line


def _compact_reason(product: Product) -> str:
    title = (getattr(product, "title", "") or "")
    saved_amount = 0.0
    for key in ("saved_amount", "discount_amount", "saved_price"):
        val = getattr(product, key, None)
        try:
            if val is not None:
                saved_amount = float(val)
                break
        except Exception:
            pass

    comments = 0
    for key in ("comments", "comment_count"):
        val = getattr(product, key, None)
        try:
            if val is not None:
                comments = int(val)
                break
        except Exception:
            pass

    shop_name = (getattr(product, "shop_name", "") or "")
    lower_title = title.lower()

    if saved_amount >= 20:
        return "价差更明显，先点开看实时页更容易判断值不值。"
    if comments >= 10000:
        return "评论沉淀更足，适合想省筛选时间时直接看。"
    if "自营" in title or "旗舰" in shop_name:
        return "店铺确定性更高，适合想省心下单的人。"
    if "儿童" in title or "宝宝" in title or "母婴" in lower_title:
        return "这类商品更偏省心决策，先看详情再下单更稳。"
    return "信息已经比较完整，适合先看详情后再决定。"



def get_today_recommend_text_segments(db: Session, wechat_openid: str) -> list[str]:
    batch = _select_today_batch(db, wechat_openid=wechat_openid)
    total = len(batch)
    if not batch:
        return []

    segments: list[str] = []
    for idx, product in enumerate(batch, start=1):
        title = html.unescape(str(getattr(product, "title", "") or getattr(product, "sku_name", "") or "商品"))
        lines: list[str] = []
        if idx == 1:
            lines.extend(
                [
                    f"🔥 今日推荐 {total} 个，可直接购买：",
                    "",
                ]
            )
        lines.extend(
            [
                f"{title}",
                _format_price_line(product),
                f"✨ 推荐理由：{_commercial_reason(product)}",
                f"📄 图文详情：{_detail_url(product, scene='today_recommend', slot=idx, wechat_openid=wechat_openid)}",
                f"🛒 下单链接：{_promotion_url(product, scene='today_recommend', slot=idx, wechat_openid=wechat_openid)}",
                f"🔎 更多同类产品：{_more_like_this_url(product, scene='today_recommend', slot=idx, wechat_openid=wechat_openid)}",
            ]
        )
        if idx == total:
            lines.extend(
                [
                    "",
                    "👉 再点一次“今日推荐”，继续下一组 3 个。",
                ]
            )
        segments.append("\n".join(lines).strip())

    return segments


def get_today_recommend_text_reply(db: Session, wechat_openid: str) -> str | None:
    segments = get_today_recommend_text_segments(db, wechat_openid)
    return segments[0] if segments else None


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
    .badges{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;}}
    .badge{{display:inline-flex;align-items:center;padding:6px 10px;border-radius:999px;background:#f1f5f9;color:#334155;font-size:12px;font-weight:700;}}
    .match{{margin-top:12px;color:#0f172a;font-size:13px;font-weight:700;}}
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


def _recommend_reason_short(product: Product) -> str:
    saved = _saved_amount(product)
    sales = _to_int(getattr(product, "sales_volume", None))
    merchant = _to_float(getattr(product, "merchant_health_score", None))
    flagship = _is_flagship_or_self_operated(product)

    if saved >= 20 and sales >= 1000:
        return _copy_text("h5_reason_templates", "high_save_hot", "价差已经拉开，销量也稳，适合直接看实时到手价。")
    if saved >= 10:
        return _copy_text("h5_reason_templates", "high_save", "当前有明显价差，先看实时页确认到手门槛更划算。")
    if sales >= 10000:
        return _copy_text("h5_reason_templates", "hot", "这类商品销量更稳，适合少比价、先看实时页。")
    if flagship or merchant >= 85:
        return _copy_text("h5_reason_templates", "flagship", "店铺确定性更高，适合想省心下单时优先看一眼。")
    return _copy_text("h5_reason_templates", "default", "信息已经比较完整，先看实时页再决定是否下单。")


def _recommend_reason_tags(product: Product) -> list[str]:
    saved = _saved_amount(product)
    effective = _effective_price(product)
    sales = _to_int(getattr(product, "sales_volume", None))
    merchant = _to_float(getattr(product, "merchant_health_score", None))
    flagship = _is_flagship_or_self_operated(product)

    tags: list[str] = []
    if saved >= 10:
        tags.append(_copy_text("reason_tag_labels", "save", "价差明显"))
    elif effective > 0:
        tags.append(_copy_text("reason_tag_labels", "price", "到手可看"))

    if sales >= 10000:
        tags.append(_copy_text("reason_tag_labels", "hot", "销量稳定"))
    elif sales >= 1000:
        tags.append(_copy_text("reason_tag_labels", "warm", "热销中"))

    if flagship or merchant >= 85:
        tags.append(_copy_text("reason_tag_labels", "flagship", "店铺省心"))

    uniq: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag and tag not in seen:
            uniq.append(tag)
            seen.add(tag)
    return uniq[:3]


def _same_reason_text(*, same_shop: bool, same_brand: bool, same_cat: bool, same_use: bool) -> str:
    labels: list[str] = []
    if same_shop:
        labels.append(_copy_text("match_reason_labels", "same_shop", "同店铺"))
    elif same_brand:
        labels.append(_copy_text("match_reason_labels", "same_brand", "同品牌"))
    if same_cat:
        labels.append(_copy_text("match_reason_labels", "same_category", "同类目"))
    if same_use and not same_cat:
        labels.append(_copy_text("match_reason_labels", "same_use", "同用途"))
    if labels:
        return " / ".join(labels[:2])
    return _copy_text("match_reason_labels", "fallback", "相似用途")


def render_product_h5(product: Product, *, scene: str = "", slot: str = "", wechat_openid: str = "") -> str:
    def _clean(value: object) -> str:
        return html.escape(html.unescape(str(value or "")), quote=True)

    title_raw = html.unescape(str(getattr(product, "title", "") or getattr(product, "sku_name", "") or "商品详情"))
    title_html = _clean(title_raw)
    value_html = _clean(_news_value_line(product))
    price_html = _clean(_format_price_line(product))
    reason_html = _clean(_recommend_reason_short(product))
    section_reason_title = _clean(_copy_text("section_copy", "h5_reason_title", "为什么值得看"))
    price_prefix = _clean(_copy_text("section_copy", "h5_price_prefix", "到手参考："))

    shop_name = html.unescape(str(getattr(product, "shop_name", "") or getattr(product, "merchant_name", "") or ""))
    shop_html = f'<div class="meta">店铺：{_clean(shop_name)}</div>' if shop_name else ""

    tags = _recommend_reason_tags(product)
    badges_html = ""
    if tags:
        badges_html = '<div class="badges">' + "".join(f'<span class="badge">{_clean(x)}</span>' for x in tags) + '</div>'

    image_candidates = [
        getattr(product, "image_url", ""),
        getattr(product, "main_image_url", ""),
        getattr(product, "image", ""),
        getattr(product, "white_image", ""),
    ]
    hero_url = next((str(x).strip() for x in image_candidates if str(x or "").strip()), "")
    hero_html = f'<img class="hero" src="{_clean(hero_url)}" alt="{title_html}" />' if hero_url else ""

    detail_scene = str(scene or "today_recommend")
    detail_slot = str(slot or "1")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>{title_html}</title>
  <style>
    body{{margin:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f172a;}}
    .wrap{{max-width:760px;margin:0 auto;padding:18px 16px 40px;}}
    .card{{background:#fff;border-radius:20px;padding:18px;box-shadow:0 6px 24px rgba(15,23,42,.06);margin-bottom:16px;}}
    .title{{font-size:22px;font-weight:800;line-height:1.5;margin:14px 0 0;}}
    .meta{{margin-top:10px;color:#64748b;line-height:1.8;font-size:14px;}}
    .price{{margin-top:14px;padding:14px;border-radius:14px;background:#fff7ed;color:#9a3412;line-height:1.8;font-weight:800;font-size:18px;}}
    .price-detail{{margin-top:10px;color:#64748b;line-height:1.8;font-size:14px;}}
    .reason-title{{margin-top:14px;font-size:14px;font-weight:800;color:#0f172a;}}
    .reason{{margin-top:8px;color:#334155;line-height:1.8;}}
    .hero{{width:100%;border-radius:16px;background:#fff;object-fit:cover;display:block;}}
    .badges{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;}}
    .badge{{display:inline-flex;align-items:center;padding:6px 10px;border-radius:999px;background:#f1f5f9;color:#334155;font-size:12px;font-weight:700;}}
    .actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;}}
    .btn{{display:inline-block;padding:12px 16px;border-radius:12px;text-decoration:none;font-weight:700;}}
    .btn-primary{{background:#0f172a;color:#fff;}}
    .btn-secondary{{background:#e2e8f0;color:#0f172a;}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      {hero_html}
      <div class="title">{title_html}</div>
      {shop_html}
      <div class="price">{value_html}</div>
      <div class="price-detail">{price_prefix}{price_html}</div>
      {badges_html}
      <div class="reason-title">{section_reason_title}</div>
      <div class="reason">{reason_html}</div>
      <div class="actions">
        <a class="btn btn-primary" href="{_promotion_url(product, scene=detail_scene, slot=detail_slot, wechat_openid=wechat_openid)}">下单链接</a>
        <a class="btn btn-secondary" href="{_more_like_this_url(product, scene=detail_scene, slot=detail_slot, wechat_openid=wechat_openid)}">更多同类产品</a>
      </div>
    </div>
  </div>
</body>
</html>"""


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

    rows = [x for x in _active_recommend_products(db) if int(x.id) != int(product_id)]

    generic_tokens = {
        "京东", "自营", "官方", "旗舰", "旗舰店", "品牌", "品牌店", "专卖店", "专营店",
        "商品", "礼盒", "套装", "活动", "家用", "便携", "ml", "l", "kg", "g", "盒", "袋", "瓶", "支", "片",
    }

    def _norm_tokens(text: str) -> list[str]:
        raw = re.findall(r"[a-z0-9\u4e00-\u9fff]+", str(text or "").lower())
        out: list[str] = []
        for tok in raw:
            if tok.isdigit() or len(tok) < 2:
                continue
            if tok in generic_tokens:
                continue
            out.append(tok)
        return out

    def _brand_tokens(product: Product) -> set[str]:
        out: set[str] = set()
        shop = _shop_key(product)
        if shop:
            out.add(shop)
        title = str(getattr(product, "title", "") or "")
        for tok in _norm_tokens(title):
            out.add(tok)
            if len(out) >= 6:
                break
        return out

    base_cat = _category_key(base_product)
    base_shop = _shop_key(base_product)
    base_brand = _brand_tokens(base_product)
    base_tokens = set(_norm_tokens(str(getattr(base_product, "title", "") or "")))

    scored: list[tuple[int, str, Product]] = []
    for x in rows:
        cand_cat = _category_key(x)
        cand_shop = _shop_key(x)
        cand_brand = _brand_tokens(x)
        cand_tokens = set(_norm_tokens(str(getattr(x, "title", "") or "")))

        same_cat = bool(base_cat and cand_cat and cand_cat == base_cat)
        same_shop = bool(base_shop and cand_shop and cand_shop == base_shop)
        same_brand = bool(base_brand and cand_brand and (base_brand & cand_brand))
        token_overlap = base_tokens & cand_tokens
        same_use = len(token_overlap) >= 2 or (same_cat and len(token_overlap) >= 1)

        if not (same_shop or same_brand or same_use):
            continue

        score = 0
        if same_shop:
            score += 5
        if same_brand:
            score += 5
        if same_cat:
            score += 4
        score += min(len(token_overlap), 3) * 2

        match_reason = _same_reason_text(
            same_shop=same_shop,
            same_brand=same_brand,
            same_cat=same_cat,
            same_use=same_use,
        )
        scored.append((score, match_reason, x))

    scored = sorted(
        scored,
        key=lambda item: (
            item[0],
            _score(item[2]),
            _to_int(getattr(item[2], "sales_volume", None)),
            int(getattr(item[2], "id", 0) or 0),
        ),
        reverse=True,
    )

    picked: list[Product] = []
    seen_ids: set[int] = set()
    seen_titles: set[str] = set()
    for _, match_reason, x in scored:
        pid = int(x.id)
        titlek = _title_key(x)
        if pid in seen_ids or titlek in seen_titles:
            continue
        setattr(x, "_match_reason_text", match_reason)
        picked.append(x)
        seen_ids.add(pid)
        seen_titles.add(titlek)
        if len(picked) >= 3:
            break

    rows = picked

    cards: list[str] = []
    scene_val = scene or "more_like_this"
    slot_base = _to_int(slot or 0)

    for idx, x in enumerate(rows, 1):
        title = html.escape(str(getattr(x, "title", "") or ""))
        shop_name = html.escape(str(getattr(x, "shop_name", "") or ""))
        shop_html = f'<div class="meta">店铺：{shop_name}</div>' if shop_name else ""
        value_text = html.escape(_news_value_line(x))
        price_text = html.escape(_format_price_line(x))
        reason_text = html.escape(_recommend_reason_short(x))
        match_prefix = html.escape(_copy_text("section_copy", "more_like_this_match_prefix", "匹配："))
        match_reason = html.escape(str(getattr(x, "_match_reason_text", "") or _copy_text("match_reason_labels", "fallback", "相似用途")))
        tags = _recommend_reason_tags(x)
        badges_html = ""
        if tags:
            badges_html = '<div class="badges">' + "".join(f'<span class="badge">{html.escape(str(tag))}</span>' for tag in tags) + '</div>'

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
              <div class="match">{match_prefix}{match_reason}</div>
              {shop_html}
              <div class="price">{value_text}</div>
              <div class="meta">{html.escape(_copy_text("section_copy", "h5_price_prefix", "到手参考："))}{price_text}</div>
              {badges_html}
              <div class="reason">{reason_text}</div>
              <div class="actions">
                <a class="btn btn-primary" href="{buy_link}">{html.escape(LABEL_BUY)}</a>
              </div>
            </div>
            """.strip()
        )

    intro = f"""
    <div class="card">
      <div class="title">{html.escape(_copy_text("section_copy", "more_like_this_title", "更多同类产品"))}</div>
      <div class="meta">{html.escape(_copy_text("section_copy", "more_like_this_intro", "优先按同品牌 / 同用途 / 同类目补充 1-3 个更接近的商品；不够接近就不乱塞。"))}</div>
    </div>
    """.strip()

    if rows:
        body = intro + "\n" + "\n".join(cards)
    else:
        empty_title = html.escape(_copy_text("section_copy", "more_like_this_empty_title", "当前商品池里还没有足够接近的同类商品。"))
        empty_desc = html.escape(_copy_text("section_copy", "more_like_this_empty_desc", "宁可少推荐，也不乱塞不相关商品。"))
        body = intro + "\n" + f'<div class="card"><div class="title">{empty_title}</div><div class="meta">{empty_desc}</div></div>'

    return _html_shell(_copy_text("section_copy", "more_like_this_title", "更多同类产品"), body)

# === today recommend news article builder start ===
def _product_pic_url(product: Product) -> str:
    for key in ("image_url", "main_image_url", "image", "white_image"):
        val = str(getattr(product, key, "") or "").strip()
        if val:
            return val
    return ""


def _sales_volume_label(product: Product) -> str:
    sales = _to_int(getattr(product, "sales_volume", None))
    if sales < 100:
        return ""
    if sales >= 10000:
        return f"热销{sales / 10000:.1f}万+".replace(".0万+", "万+")
    return f"热销{sales}+"

def _news_value_line(product: Product) -> str:
    saved = _saved_amount(product)
    effective = _effective_price(product)
    sales_text = _sales_volume_label(product)

    if saved > 0:
        if saved >= 10:
            left = f"省¥{saved:.0f}"
        else:
            left = f"省¥{saved:.2f}".rstrip("0").rstrip(".")
    elif effective > 0:
        left = f"到手¥{effective:.2f}".rstrip("0").rstrip(".")
    else:
        left = "点开看实时价"

    if sales_text:
        return f"{left}｜{sales_text}"
    return left

def _news_description_for_product(product: Product) -> str:
    text = _news_value_line(product).replace("\n", " ").strip()
    return text[:120]

def _news_title_for_product(product: Product) -> str:
    value = _news_value_line(product).replace("｜", " ").strip()
    if not value:
        return _wechat_safe_title(product, limit=24).strip() or "商品"

    max_total = 28
    available = max(8, max_total - len(value) - 1)
    core = _wechat_safe_title(product, limit=available).strip() or "商品"
    title = f"{core}｜{value}"
    if len(title) <= max_total:
        return title

    core = _wechat_safe_title(product, limit=max(6, available - 2)).strip() or "商品"
    return f"{core}｜{value}"[:max_total]

def get_today_recommend_news_articles(db: Session, wechat_openid: str) -> list[dict[str, str]]:
    batch = _select_today_batch(db, wechat_openid=wechat_openid)
    if not batch:
        return []

    _record_scene_exposures(
        db,
        openid_hash=_openid_key(wechat_openid),
        scene="today_recommend",
        products=batch,
    )

    articles: list[dict[str, str]] = []
    for idx, product in enumerate(batch, 1):
        title = _news_title_for_product(product)

        articles.append(
            {
                "title": title,
                "description": _news_description_for_product(product),
                "pic_url": _product_pic_url(product),
                "url": _detail_url(
                    product,
                    scene="today_recommend",
                    slot=idx,
                    wechat_openid=wechat_openid,
                ),
            }
        )

    return articles
# === today recommend news article builder end ===
