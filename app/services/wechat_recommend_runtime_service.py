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
from app.services.user_crypto_service import hash_identity


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
    return_policy = cfg.get("return_risk_policy") or {}
    min_good_comment_rate = _to_float(return_policy.get("min_good_comment_rate", 0))
    min_comment_count = _to_int(return_policy.get("min_comment_count", 0))

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

    good_comments_share = _to_float(getattr(product, "good_comments_share", None))
    comment_count = _to_int(getattr(product, "comment_count", None))
    if min_good_comment_rate > 0 and good_comments_share > 0 and good_comments_share < min_good_comment_rate:
        return False
    if min_comment_count > 0 and comment_count > 0 and comment_count < min_comment_count:
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




def _prioritize_price_verified_products(products: list[Product]) -> list[Product]:
    """Prefer products with refreshed/exact JD price snapshot before user-facing recommendation."""
    price_display_cfg = _cfg().get("price_display") or {}
    if isinstance(price_display_cfg, dict) and not price_display_cfg.get("prefer_verified_in_recommendation", True):
        return products

    def rank(product: Product) -> tuple[int, int, float, int, int]:
        exact = 1 if bool(getattr(product, "is_exact_discount", False)) and bool(getattr(product, "price_verified_at", None)) else 0
        verified = 1 if bool(getattr(product, "price_verified_at", None)) else 0
        score = _score(product)
        sales = _to_int(getattr(product, "sales_volume", None))
        pid = _to_int(getattr(product, "id", None))
        return exact, verified, score, sales, pid

    return sorted(products, key=rank, reverse=True)

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
    # Per-user dedup key. Uses HMAC-SHA256, not raw openid or plain SHA1.
    return str(hash_identity(str(openid)) or "")[:64]


def _promotion_url(product: Product, *, wechat_openid: str, scene: str, slot: int) -> str:
    tpl = str(
        _url_cfg().get("promotion_redirect_path_template")
        or "/promotion/redirect?wechat_openid={wechat_openid}&product_id={product_id}&scene={scene}&slot={slot}"
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
        or "/h5/recommend/{product_id}?scene={scene}&slot={slot}"
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
        or "/h5/recommend/more-like-this?product_id={product_id}&scene={scene}&slot={slot}"
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

def _price_display_cfg() -> dict[str, Any]:
    val = _cfg().get("price_display") or {}
    return val if isinstance(val, dict) else {}


def _money_text(value: float) -> str:
    try:
        num = float(value or 0)
    except Exception:
        return "0"
    if abs(num - int(num)) < 0.000001:
        return str(int(num))
    return f"{num:.2f}".rstrip("0").rstrip(".")


def _sales_display_text(product: Product) -> str:
    cfg = _price_display_cfg()
    sales = _to_int(getattr(product, "sales_volume", None))
    if sales <= 0:
        return ""
    if sales >= 10000:
        return f"{sales // 10000}{cfg.get('sales_wan_unit') or '万+'}"
    return f"{sales}{cfg.get('sales_unit') or '+'}"


def _price_snapshot_for_display(product: Product) -> dict[str, Any]:
    jd_price = _to_float(getattr(product, "price", None))
    coupon_price = _to_float(getattr(product, "coupon_price", None))
    purchase_price = _to_float(getattr(product, "purchase_price", None))
    basis_price = _to_float(getattr(product, "basis_price", None))

    purchase = purchase_price if purchase_price > 0 else 0.0
    if purchase <= 0 and coupon_price > 0:
        purchase = coupon_price
    if purchase <= 0 and jd_price > 0:
        purchase = jd_price

    basis = basis_price if basis_price > 0 else jd_price
    saved = round(basis - purchase, 2) if basis > 0 and purchase > 0 and purchase < basis else 0.0

    return {
        "purchase": purchase,
        "basis": basis,
        "saved": saved,
        "has_compare_price": bool(purchase > 0 and basis > 0 and saved > 0),
        "has_single_price": bool(purchase > 0),
        "sales_text": _sales_display_text(product),
    }


def _fmt_tpl(template: str, **kwargs: Any) -> str:
    try:
        return str(template or "").format(**kwargs)
    except Exception:
        return str(template or "")


def _price_advantage_text(product: Product) -> tuple[str, str]:
    cfg = _price_display_cfg()
    snap = _price_snapshot_for_display(product)
    sales_text = str(snap.get("sales_text") or "")

    if snap.get("has_compare_price"):
        key = "numeric_main_template" if sales_text else "numeric_main_template_no_sales"
        main = _fmt_tpl(
            cfg.get(key) or "到手约¥{purchase}｜京东官网价¥{basis}｜可省¥{saved}",
            purchase=_money_text(float(snap["purchase"])),
            basis=_money_text(float(snap["basis"])),
            saved=_money_text(float(snap["saved"])),
            sales_text=sales_text,
        )
        return main, str(cfg.get("numeric_sub_text") or "先到先得，看得见的优惠；库存、地区和优惠券以京东下单页可领取状态为准。")

    if snap.get("has_single_price"):
        key = "single_price_template" if sales_text else "single_price_template_no_sales"
        main = _fmt_tpl(
            cfg.get(key) or "到手约¥{purchase}",
            purchase=_money_text(float(snap["purchase"])),
            sales_text=sales_text,
        )
        return main, str(cfg.get("numeric_sub_text") or "先到先得，看得见的优惠；库存、地区和优惠券以京东下单页可领取状态为准。")

    if sales_text:
        return _fmt_tpl(
            cfg.get("live_main_template") or "热销{sales_text}｜点开看当前可用券",
            sales_text=sales_text,
        ), str(cfg.get("live_sub_text") or "点开京东下单页可看到当前可用券、实时到手价和库存。")

    return str(cfg.get("live_main_no_sales") or "点开看当前可用券"), str(cfg.get("live_sub_text") or "点开京东下单页可看到当前可用券、实时到手价和库存。")


def _price_advantage_main(product: Product) -> str:
    return _price_advantage_text(product)[0]


def _price_advantage_sub(product: Product) -> str:
    return _price_advantage_text(product)[1]


def _format_price_line(product: Product) -> str:
    return _price_advantage_main(product)


def _news_value_line(product: Product) -> str:
    return _price_advantage_main(product)


def _commercial_reason(product: Product) -> str:
    cfg = _cfg().get("commercial_reason") or {}
    cfg = cfg if isinstance(cfg, dict) else {}
    snap = _price_snapshot_for_display(product)

    sales = _to_int(getattr(product, "sales_volume", None))
    has_sales = sales >= 300
    has_shop = _is_flagship_or_self_operated(product) or bool(_shop_name(product))

    if snap.get("has_compare_price") and has_shop and has_sales:
        return str(cfg.get("discount_shop_sales") or "品牌/店铺确定性更高，当前有可对比价差，也有购买热度；如符合当前需求，建议入手。")
    if snap.get("has_compare_price") and has_sales:
        return str(cfg.get("discount_sales") or "当前有可对比价差，也有购买热度；如符合当前需求，建议入手。")
    if snap.get("has_compare_price"):
        return str(cfg.get("discount") or "当前价格优势清晰，适合需要这类商品时直接入手。")
    if has_shop and has_sales:
        return str(cfg.get("shop_sales") or "品牌/店铺确定性更高，已有购买热度；如符合当前需求，建议入手。")
    if has_sales:
        return str(cfg.get("sales") or "已有购买热度，适合想省时间筛选时直接查看；符合需求可以入手。")
    if has_shop:
        return str(cfg.get("shop") or "品牌/店铺确定性更高，适合对品质和售后稳定性有要求的用户优先入手。")
    return str(cfg.get("fallback") or "商品信息、销量和店铺维度已完成初步筛选；如符合当前需求，可以入手。")


def _compact_reason(product: Product) -> str:
    return _commercial_reason(product)


def _recommend_reason_short(product: Product) -> str:
    return _commercial_reason(product)


def _today_batch_title(db: Session, *, wechat_openid: str) -> str:
    cfg = _cfg().get("today_batch_h5") or {}
    cfg = cfg if isinstance(cfg, dict) else {}
    first_title = str(cfg.get("first_title") or "首批今日优选好物推荐")
    next_title = str(cfg.get("next_title") or "新一批今日优选好物推荐")

    try:
        openid_hash = _openid_key(wechat_openid)
        exposure_count = (
            db.query(WechatRecommendExposure.product_id)
            .filter(
                WechatRecommendExposure.openid_hash == openid_hash,
                WechatRecommendExposure.scene == "today_recommend",
            )
            .count()
        )
        return next_title if exposure_count > 3 else first_title
    except Exception:
        return first_title



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
    return _prioritize_price_verified_products(_filter_commercial_proactive_pool(rows))


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


MENU_CROSS_DEDUP_SCENES = {"today_recommend", "find_product_entry"}


def _dedup_scenes(scene: str) -> list[str]:
    if scene in MENU_CROSS_DEDUP_SCENES:
        return sorted(MENU_CROSS_DEDUP_SCENES)
    return [scene]


def _recent_scene_product_ids(db: Session, *, openid_hash: str, scene: str) -> set[int]:
    try:
        rows = (
            db.query(WechatRecommendExposure.product_id)
            .filter(
                WechatRecommendExposure.openid_hash == openid_hash,
                WechatRecommendExposure.scene.in_(_dedup_scenes(scene)),
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
                WechatRecommendExposure.scene.in_(_dedup_scenes(scene)),
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
    from app.services.wechat_find_product_entry_config_service import load_find_product_entry_config

    cfg = load_find_product_entry_config()
    product = _find_entry_product(db, wechat_openid=wechat_openid)
    if not product:
        return str(cfg.get("fallback_text") or "").strip()

    _record_scene_exposures(
        db,
        openid_hash=_openid_key(wechat_openid),
        scene="find_product_entry",
        products=[product],
    )

    labels = cfg.get("labels") if isinstance(cfg.get("labels"), dict) else {}
    value_templates = cfg.get("value_templates") if isinstance(cfg.get("value_templates"), dict) else {}

    def label(key: str) -> str:
        return str(labels.get(key) or "").strip()

    def tpl(key: str) -> str:
        return str(value_templates.get(key) or "").strip()

    separator = str(cfg.get("separator") or "：")
    title = str(getattr(product, "title", "") or cfg.get("default_product_title") or "").strip()
    category = str(getattr(product, "category_name", "") or "").strip()
    shop = str(getattr(product, "shop_name", "") or "").strip()
    sales = _to_int(getattr(product, "sales_volume", 0))
    price = _effective_price(product)
    saved = _saved_amount(product)

    value_bits = []
    if price > 0 and tpl("price"):
        value_bits.append(tpl("price").format(price=price))
    if saved > 0 and tpl("saved"):
        value_bits.append(tpl("saved").format(saved=saved))
    if sales > 0:
        if sales >= 10000 and tpl("sales_wan"):
            value_bits.append(tpl("sales_wan").format(sales_wan=sales // 10000, sales=sales))
        elif tpl("sales_count"):
            value_bits.append(tpl("sales_count").format(sales=sales))

    value_line = "｜".join(value_bits) or str(cfg.get("default_value_line") or "").strip()
    detail_url = _detail_url(product, scene="find_product_entry", slot=1, wechat_openid=wechat_openid)
    buy_url = _promotion_url(product, wechat_openid=wechat_openid, scene="find_product_entry", slot=1)
    more_url = _more_like_this_url(product, scene="find_product_entry", slot=1, wechat_openid=wechat_openid)
    reason = _commercial_reason(product)

    try:
        limit = int(cfg.get("short_title_limit") or 78)
    except Exception:
        limit = 78
    short_title = title[:limit] + ("…" if len(title) > limit else "")

    lines = [str(x) for x in cfg.get("header_lines", []) if x is not None]

    def add_labeled_line(key: str, value: str) -> None:
        value = str(value or "").strip()
        if not value:
            return
        prefix = label(key)
        lines.append(f"{prefix}{separator}{value}" if prefix else value)

    product_prefix = label("product")
    lines.append(f"{product_prefix} {short_title}".strip())
    add_labeled_line("value", value_line)
    add_labeled_line("category", category)
    add_labeled_line("shop", shop)
    add_labeled_line("reason", reason)
    add_labeled_line("tip", str(cfg.get("conversion_tip") or ""))

    lines.append("")
    add_labeled_line("detail", detail_url)
    add_labeled_line("buy", buy_url)
    add_labeled_line("more", more_url)

    return '\n'.join(lines).strip()




def _short_title(value: str, limit: int = 24) -> str:
    text = str(value or "").strip()
    if not text:
        return "优选商品"
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)] + "…"


def get_find_product_entry_news_articles(db: Session, wechat_openid: str) -> list[dict[str, str]]:
    product = _find_entry_product(db, wechat_openid=wechat_openid)
    if not product:
        return []

    _record_scene_exposures(
        db,
        openid_hash=_openid_key(wechat_openid),
        scene="find_product_entry",
        products=[product],
    )

    title = _short_title(str(getattr(product, "title", "") or "优选商品"), 24)
    desc = f"{_news_value_line(product)}｜也可以直接回复：洗衣液 / 牙膏 / 宝宝湿巾 / 京东自营"
    return [
        {
            "title": title[:28],
            "description": desc[:120],
            "pic_url": _product_pic_url(product),
            "url": _detail_url(
                product,
                scene="find_product_entry",
                slot=1,
                wechat_openid=wechat_openid,
            ),
        }
    ]


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


def _has_exact_verified_price(product: Product) -> bool:
    """Only show numeric coupon/official price when JD exact-price verification succeeded."""
    try:
        return bool(getattr(product, "is_exact_discount", False)) and bool(getattr(product, "price_verified_at", None))
    except Exception:
        return False


def _exact_verified_price_copy(product: Product, *, labels: dict, sections: dict) -> tuple[str, str]:
    def label(key: str, fallback: str = "") -> str:
        return str(labels.get(key) or fallback).strip()

    def section(key: str, fallback: str = "") -> str:
        return str(sections.get(key) or fallback).strip()

    sales = _to_int(getattr(product, "sales_volume", None))
    sales_text = ""
    if sales > 0:
        if sales >= 10000:
            sales_text = f"{sales // 10000}万+"
        else:
            sales_text = f"{sales}+"

    if _has_exact_verified_price(product):
        purchase = _to_float(getattr(product, "purchase_price", None)) or _effective_price(product)
        basis = _to_float(getattr(product, "basis_price", None)) or _to_float(getattr(product, "price", None))
        saved = basis - purchase if basis > 0 and purchase > 0 and basis > purchase else _saved_amount(product)

        parts = []
        if purchase > 0:
            parts.append(f"{label('purchase_price', '优惠价')}¥{purchase:g}")
        if basis > 0 and basis >= purchase:
            parts.append(f"{label('jd_official_price', '京东官网价')}¥{basis:g}")
        if saved > 0:
            parts.append(f"{label('saved', '立省')}¥{saved:g}")
        if sales_text:
            parts.append(f"{label('sales_prefix', '热销')}{sales_text}")

        if parts:
            return "｜".join(parts), section("price_note_verified", "该价格已通过京东接口刷新；下单前仍可在京东页面确认当前可用券、实时到手价和库存。")

    fallback = label("live_price", "") or section("fallback_price", "点开京东看实时券价")
    if sales_text:
        fallback = f"{fallback}｜{label('sales_prefix', '热销')}{sales_text}"
    return fallback, section("price_note_unverified", "优惠、券、地区和库存会实时变化，点开京东下单页可看到当前可用券和实时到手价。")


def render_product_h5(product: Product, *, scene: str = "", slot: str = "", wechat_openid: str = "") -> str:
    from app.services.wechat_find_product_entry_config_service import load_find_product_entry_config

    cfg = load_find_product_entry_config()
    h5_cfg = cfg.get("h5_detail") if isinstance(cfg.get("h5_detail"), dict) else {}
    labels = h5_cfg.get("labels") if isinstance(h5_cfg.get("labels"), dict) else {}
    sections = h5_cfg.get("sections") if isinstance(h5_cfg.get("sections"), dict) else {}
    badges = h5_cfg.get("badges") if isinstance(h5_cfg.get("badges"), dict) else {}
    empty = h5_cfg.get("empty") if isinstance(h5_cfg.get("empty"), dict) else {}
    button_cfg = cfg.get("h5_buttons") if isinstance(cfg.get("h5_buttons"), dict) else {}

    def c(value: object) -> str:
        return html.escape(html.unescape(str(value or "")), quote=True)

    def label(key: str) -> str:
        return str(labels.get(key) or key).strip()

    def text(section_key: str) -> str:
        return str(sections.get(section_key) or "").strip()

    def empty_text(key: str) -> str:
        return str(empty.get(key) or "").strip()

    def first_attr(*names: str) -> object:
        for name in names:
            value = getattr(product, name, None)
            if value not in (None, ""):
                return value
        return ""

    def num_text(value: object) -> str:
        n = _to_int(value)
        if n <= 0:
            return ""
        if n >= 10000:
            return f"{n // 10000}万+"
        return f"{n}+"

    def rate_text(value: object) -> str:
        try:
            raw = float(value or 0)
        except Exception:
            return ""
        if raw <= 0:
            return ""
        if raw <= 1:
            raw = raw * 100
        return f"{raw:.1f}%".rstrip("0").rstrip(".")

    title_raw = html.unescape(str(getattr(product, "title", "") or getattr(product, "sku_name", "") or label("detail_title")))
    title_html = c(title_raw)

    category = str(first_attr("category_name", "category", "cid_name") or "")
    shop_name = str(first_attr("shop_name", "merchant_name", "vendor_name") or "")
    shop_score = str(first_attr("shop_score", "shop_rating", "shop_star", "dsr_score", "score") or "")
    shop_sales = num_text(first_attr("shop_sales_volume", "shop_order_count", "shop_total_sales", "total_sales", "order_count"))
    sales = num_text(first_attr("sales_volume", "order_count_30d", "in_order_count_30_days", "monthly_sales", "comment_count"))
    comments = num_text(first_attr("comment_count", "comments_count", "review_count", "good_comments"))
    good_rate = rate_text(first_attr("good_comment_rate", "good_comments_share", "positive_rate", "good_rate"))

    price_value = _effective_price(product)
    saved_value = _saved_amount(product)
    price_display = f"¥{price_value:g}" if price_value > 0 else empty_text("unknown")
    saved_display = f"¥{saved_value:g}" if saved_value > 0 else empty_text("no_saved")

    exact_purchase = _to_float(getattr(product, "purchase_price", None))
    exact_basis = _to_float(getattr(product, "basis_price", None))
    has_strict_verified_price = (
        bool(getattr(product, "is_exact_discount", False))
        and exact_purchase > 0
        and exact_basis > exact_purchase
    )

    sales_text = sales or ""
    if has_strict_verified_price:
        exact_saved = exact_basis - exact_purchase
        price_main_raw = f"省¥{exact_saved:g}" + (f"｜热销{sales_text}" if sales_text else "")
        price_sub_raw = (
            f"{label('estimated_price')}：优惠价￥{exact_purchase:.2f}｜京东官网价￥{exact_basis:.2f}｜立省￥{exact_saved:.2f}。"
            + text("price_verified_note")
        )
    else:
        if sales_text:
            template = text("price_unverified_main_template")
            try:
                price_main_raw = template.format(sales_text=sales_text)
            except Exception:
                price_main_raw = sales_text
        else:
            price_main_raw = text("price_unverified_main_no_sales")
        price_sub_raw = text("price_unverified_subtitle")

    value_html = c(_price_advantage_main(product))
    price_line_html = c(_price_advantage_sub(product))
    reason_html = c(_recommend_reason_short(product))

    image_candidates = [
        getattr(product, "image_url", ""),
        getattr(product, "main_image_url", ""),
        getattr(product, "image", ""),
        getattr(product, "white_image", ""),
    ]
    hero_url = next((str(x).strip() for x in image_candidates if str(x or "").strip()), "")
    hero_html = f'<img class="hero" src="{c(hero_url)}" alt="{title_html}" />' if hero_url else ""

    detail_scene = str(scene or "today_recommend")
    detail_slot = str(slot or "1")
    buy_url = _promotion_url(product, scene=detail_scene, slot=detail_slot, wechat_openid=wechat_openid)
    more_url = _more_like_this_url(product, scene=detail_scene, slot=detail_slot, wechat_openid=wechat_openid)
    buy_text = str(button_cfg.get("buy") or label("buy")).strip()
    more_text = str(button_cfg.get("more") or label("more")).strip()

    badge_keys = ["price", "sales", "shop", "ai"]
    badges_html = "".join(
        f'<span class="badge">{c(badges.get(k) or "")}</span>'
        for k in badge_keys
        if str(badges.get(k) or "").strip()
    )

    info_rows = []

    def add_info(label_key: str, value: str) -> None:
        value = str(value or "").strip()
        if value:
            info_rows.append((label(label_key), value))

    # 到手参考、预计可省已经在价格优势区展示，商品信息区不再重复。
    add_info("sales", sales)
    add_info("comments", comments)
    add_info("good_rate", good_rate)
    add_info("category", category)
    add_info("shop", shop_name)

    # 店铺评分、店铺成交如果数据源没有返回，就不展示“暂无”，避免制造无价值信息。
    add_info("shop_score", shop_score)
    add_info("shop_sales", shop_sales)

    info_html = "".join(
        f'<div class="kv"><span>{c(k)}</span><strong>{c(v)}</strong></div>'
        for k, v in info_rows
        if str(v or "").strip()
    )

    note_html = c(text("risk_note"))

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>{title_html}</title>
  <style>
    body{{margin:0;background:#f6f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f172a;}}
    .wrap{{max-width:760px;margin:0 auto;padding:14px 14px 88px;}}
    .card{{background:#fff;border-radius:20px;padding:16px;box-shadow:0 8px 28px rgba(15,23,42,.07);margin-bottom:14px;}}
    .hero{{width:100%;border-radius:18px;background:#fff;object-fit:cover;display:block;}}
    .title{{font-size:21px;font-weight:850;line-height:1.42;margin:14px 0 0;letter-spacing:-.2px;}}
    .subtitle{{margin-top:10px;color:#64748b;line-height:1.75;font-size:14px;}}
    .badges{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;}}
    .badge{{display:inline-flex;align-items:center;padding:6px 10px;border-radius:999px;background:#eef2ff;color:#3730a3;font-size:12px;font-weight:750;}}
    .pricebox{{margin-top:14px;padding:14px;border-radius:16px;background:#fff7ed;color:#9a3412;}}
    .price-main{{font-size:20px;font-weight:900;line-height:1.5;}}
    .price-sub{{margin-top:6px;font-size:13px;color:#9a3412;line-height:1.65;}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px;}}
    .kv{{background:#f8fafc;border-radius:14px;padding:10px;min-height:48px;}}
    .kv span{{display:block;color:#64748b;font-size:12px;line-height:1.4;}}
    .kv strong{{display:block;margin-top:4px;color:#0f172a;font-size:15px;line-height:1.4;word-break:break-word;}}
    .section-title{{font-size:16px;font-weight:850;margin:0 0 10px;}}
    .reason{{color:#334155;line-height:1.85;font-size:15px;}}
    .decision{{margin:0;padding-left:20px;color:#334155;line-height:1.9;font-size:15px;}}
    .risk{{margin-top:10px;color:#64748b;line-height:1.75;font-size:13px;}}
    .actions{{position:fixed;left:0;right:0;bottom:0;background:rgba(255,255,255,.96);backdrop-filter:blur(10px);box-shadow:0 -8px 24px rgba(15,23,42,.08);padding:10px 14px calc(10px + env(safe-area-inset-bottom));display:flex;gap:10px;justify-content:center;}}
    .btn{{display:block;text-align:center;padding:13px 14px;border-radius:14px;text-decoration:none;font-weight:850;font-size:15px;}}
    .btn-primary{{background:#0f172a;color:#fff;min-width:168px;}}
    .btn-secondary{{background:#e2e8f0;color:#0f172a;min-width:118px;}}
    @media (max-width:420px){{.grid{{grid-template-columns:1fr 1fr;gap:8px;}}.title{{font-size:19px;}}.btn{{font-size:14px;padding:12px 10px;}}}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      {hero_html}
      <div class="title">{title_html}</div>
      <div class="subtitle">{c(text("subtitle"))}</div>
      <div class="badges">{badges_html}</div>
      <div class="pricebox">
        <div class="price-main">{c(label("price_advantage"))}：{value_html}</div>
        <div class="price-sub">{price_line_html}</div>
      </div>
    </div>

    <div class="card">
      <div class="section-title">{c(label("detail_title"))}</div>
      <div class="grid">{info_html}</div>
    </div>

    <div class="card">
      <div class="section-title">{c(label("reason_title"))}</div>
      <div class="reason">{reason_html}</div>
    </div>

    <div class="card">
      <div class="section-title">{c(label("decision_title"))}</div>
      <div class="risk">{note_html}</div>
    </div>
  </div>

  <div class="actions">
    <a class="btn btn-primary" href="{c(buy_url)}">{c(buy_text)}</a>
    <a class="btn btn-secondary" href="{c(more_url)}">{c(more_text)}</a>
  </div>
</body>
</html>"""



def render_recommend_batch_h5(
    db: Session,
    *,
    ids: str,
    focus_id: int = 0,
    scene: str = "",
    slot: str = "",
    wechat_openid: str = "",
) -> str:
    batch_cfg = _cfg().get("today_batch_h5")
    if not isinstance(batch_cfg, dict):
        batch_cfg = {}

    labels = batch_cfg.get("labels") if isinstance(batch_cfg.get("labels"), dict) else {}
    sections = batch_cfg.get("sections") if isinstance(batch_cfg.get("sections"), dict) else {}
    reason_rules = batch_cfg.get("reason_rules") if isinstance(batch_cfg.get("reason_rules"), dict) else {}

    def c(value: object) -> str:
        return html.escape(html.unescape(str(value or "")), quote=True)

    def text(key: str) -> str:
        return str(batch_cfg.get(key) or "").strip()

    def label(key: str) -> str:
        return str(labels.get(key) or "").strip()

    def section(key: str) -> str:
        return str(sections.get(key) or "").strip()

    def rule(key: str) -> str:
        return str(reason_rules.get(key) or "").strip()

    def num_text(value: object) -> str:
        n = _to_int(value)
        if n <= 0:
            return ""
        if n >= 10000:
            return f"{n // 10000}万+"
        return f"{n}+"

    def rate_text(value: object) -> str:
        try:
            raw = float(value or 0)
        except Exception:
            return ""
        if raw <= 0:
            return ""
        if raw <= 1:
            raw *= 100
        return f"{raw:.1f}%".rstrip("0").rstrip(".")

    def price_line(product: Product) -> tuple[str, str]:
        return _exact_verified_price_copy(product, labels=labels, sections=sections)

    def reason_text(product: Product) -> str:
        saved = _saved_amount(product)
        basis = _to_float(getattr(product, "price", None))
        purchase = _effective_price(product)
        saved_rate = (saved / basis) if basis > 0 and saved > 0 else 0.0
        sales = _to_int(getattr(product, "sales_volume", None))
        comments = _to_int(getattr(product, "comment_count", None))
        shop = str(getattr(product, "shop_name", "") or "")

        if saved >= 20 or saved_rate >= 0.25:
            return rule("high_discount")
        if saved >= 5 and purchase > 0:
            return rule("meaningful_saved")
        if sales >= 1000 or comments >= 10000:
            return rule("social_proof")
        if "自营" in shop or "旗舰" in shop or "官方" in shop:
            return rule("shop_trust")
        return rule("balanced")

    product_ids: list[int] = []
    seen: set[int] = set()
    for raw in re.split(r"[,，\s]+", str(ids or "")):
        raw = raw.strip()
        if not raw.isdigit():
            continue
        pid = int(raw)
        if pid > 0 and pid not in seen:
            product_ids.append(pid)
            seen.add(pid)

    if not product_ids:
        return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>{c(text("title"))}</title></head>
<body><h1>{c(text("title"))}</h1></body>
</html>"""

    rows = db.query(Product).filter(Product.id.in_(product_ids), Product.status == "active").all()
    order = {pid: idx for idx, pid in enumerate(product_ids)}
    rows = sorted(
        rows,
        key=lambda p: (
            0 if int(getattr(p, "id", 0) or 0) == int(focus_id or 0) else 1,
            order.get(int(getattr(p, "id", 0) or 0), 999),
        ),
    )

    scene_val = str(scene or "today_recommend")
    slot_base = _to_int(slot or 0)

    def product_card(product: Product, idx: int) -> str:
        product_title = str(getattr(product, "title", "") or getattr(product, "sku_name", "") or text("fallback_product_title"))
        title = c(product_title)
        hero = _product_pic_url(product)
        hero_html = f'<img class="product-img" src="{c(hero)}" alt="{title}" />' if hero else ""

        sales = num_text(getattr(product, "sales_volume", None))
        comments = num_text(getattr(product, "comment_count", None))
        good_rate = rate_text(getattr(product, "good_comments_share", None))
        category = str(getattr(product, "category_name", "") or "").strip()
        shop = str(getattr(product, "shop_name", "") or "").strip()

        info_rows = []
        for k, v in [
            (label("sales"), sales),
            (label("comments"), comments),
            (label("good_rate"), good_rate),
            (label("category"), category),
            (label("shop"), shop),
        ]:
            if str(k or "").strip() and str(v or "").strip():
                info_rows.append((k, v))

        info_html = "".join(
            f'<div class="kv"><span>{c(k)}</span><strong>{c(v)}</strong></div>'
            for k, v in info_rows
        )

        buy_url = _promotion_url(
            product,
            scene=scene_val,
            slot=slot_base + idx,
            wechat_openid=wechat_openid,
        )
        more_url = _more_like_this_url(
            product,
            scene=scene_val,
            slot=slot_base + idx,
            wechat_openid=wechat_openid,
        )
        price_main, price_note = price_line(product)

        return f"""
        <div class="card product-card">
          {hero_html}
          <div class="title product-title">{title}</div>
          <div class="pricebox">
            <div class="price-main">{c(label("price"))}：{c(price_main)}</div>
            <div class="price-sub">{c(label("price_note"))}：{c(price_note)}</div>
          </div>
          <div class="grid">{info_html}</div>
          <div class="section-title">{c(label("reason"))}</div>
          <div class="reason">{c(reason_text(product))}</div>
          <div class="card-actions">
            <a class="btn btn-primary" href="{c(buy_url)}">{c(label("buy"))}</a>
            <a class="btn btn-secondary" href="{c(more_url)}">{c(label("more"))}</a>
          </div>
        </div>
        """.strip()

    cards = "\n".join(product_card(product, idx) for idx, product in enumerate(rows, 1))

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>{c(text("title"))}</title>
  <style>
    body{{margin:0;background:#f6f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f172a;}}
    .wrap{{max-width:760px;margin:0 auto;padding:16px 14px 40px;}}
    .page-title{{font-size:23px;font-weight:900;line-height:1.35;margin:2px 2px 16px;letter-spacing:-.2px;}}
    .card{{background:#fff;border-radius:20px;padding:16px;box-shadow:0 8px 28px rgba(15,23,42,.07);margin-bottom:14px;}}
    .title{{font-size:21px;font-weight:850;line-height:1.42;margin:0;letter-spacing:-.2px;}}
    .product-img{{width:100%;border-radius:18px;background:#fff;object-fit:cover;display:block;margin-bottom:12px;}}
    .product-title{{margin-bottom:10px;}}
    .pricebox{{margin-top:12px;padding:14px;border-radius:16px;background:#fff7ed;color:#9a3412;}}
    .price-main{{font-size:18px;font-weight:900;line-height:1.5;}}
    .price-sub{{margin-top:6px;font-size:13px;color:#9a3412;line-height:1.65;}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px;}}
    .kv{{background:#f8fafc;border-radius:14px;padding:10px;min-height:48px;}}
    .kv span{{display:block;color:#64748b;font-size:12px;line-height:1.4;}}
    .kv strong{{display:block;margin-top:4px;color:#0f172a;font-size:15px;line-height:1.4;word-break:break-word;}}
    .section-title{{font-size:16px;font-weight:850;margin:14px 0 8px;}}
    .reason{{color:#334155;line-height:1.85;font-size:15px;}}
    .card-actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;}}
    .btn{{display:block;text-align:center;padding:12px 14px;border-radius:14px;text-decoration:none;font-weight:850;font-size:15px;}}
    .btn-primary{{background:#0f172a;color:#fff;min-width:168px;}}
    .btn-secondary{{background:#e2e8f0;color:#0f172a;min-width:118px;}}
    .footer{{color:#64748b;line-height:1.75;font-size:13px;}}
    @media (max-width:420px){{.grid{{grid-template-columns:1fr 1fr;gap:8px;}}.title{{font-size:19px;}}.page-title{{font-size:22px;}}.btn{{font-size:14px;padding:12px 10px;}}}}
  </style>
</head>
<body>
  <div class="wrap">
    <h1 class="page-title">{c(text("title"))}</h1>
    {cards}
    <div class="card footer">{c(text("footer_note"))}</div>
  </div>
</body>
</html>"""


def render_today_batch_h5(
    db: Session,
    *,
    ids: str = "",
    focus_id: str | int = "",
    scene: str = "",
    slot: str = "",
    wechat_openid: str = "",
    **kwargs: Any,
) -> str:
    cfg = _cfg().get("today_batch_h5") or {}
    cfg = cfg if isinstance(cfg, dict) else {}

    raw_ids = ids or kwargs.get("product_ids") or kwargs.get("product_id_list") or ""
    if isinstance(raw_ids, (list, tuple)):
        id_list = [int(x) for x in raw_ids if str(x).strip().isdigit()]
    else:
        id_list = [int(x) for x in re.findall(r"\d+", str(raw_ids or ""))]

    seen: set[int] = set()
    clean_ids: list[int] = []
    for pid in id_list:
        if pid > 0 and pid not in seen:
            clean_ids.append(pid)
            seen.add(pid)

    products: list[Product] = []
    if clean_ids:
        rows = db.query(Product).filter(Product.id.in_(clean_ids)).all()
        by_id = {int(row.id): row for row in rows}
        products = [by_id[pid] for pid in clean_ids if pid in by_id]

    if not products:
        title = html.escape(str(cfg.get("empty_title") or "当前推荐商品暂不可用"))
        desc = html.escape(str(cfg.get("empty_desc") or "可以回到公众号继续点击“今日推荐”，我会重新给你换一批。"))
        return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>{title}</title></head>
<body style="margin:0;background:#f6f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f172a;">
  <div style="max-width:760px;margin:0 auto;padding:18px 14px;">
    <div style="background:#fff;border-radius:20px;padding:18px;box-shadow:0 8px 28px rgba(15,23,42,.07);">
      <h1 style="font-size:22px;line-height:1.4;margin:0 0 10px;">{title}</h1>
      <div style="color:#64748b;line-height:1.8;">{desc}</div>
    </div>
  </div>
</body>
</html>"""

    try:
        focus_int = int(focus_id or 0)
    except Exception:
        focus_int = 0
    if focus_int:
        products = sorted(products, key=lambda p: 0 if int(p.id) == focus_int else 1)

    page_title = _today_batch_title(db, wechat_openid=wechat_openid)
    price_label = str(cfg.get("price_label") or "价格优势")
    info_title = str(cfg.get("info_title") or "商品信息")
    reason_title = str(cfg.get("reason_title") or "推荐理由")
    buy_text = str(cfg.get("buy_button") or "点击我去京东快捷下单")
    more_text = str(cfg.get("more_button") or "更多类似商品")
    scene_val = str(scene or "today_recommend")

    def c(value: object) -> str:
        return html.escape(html.unescape(str(value or "")), quote=True)

    def info_rows(product: Product) -> str:
        rows: list[tuple[str, str]] = []
        sales_text = _sales_display_text(product)
        comments = _to_int(getattr(product, "comment_count", None))
        good_rate_raw = _to_float(getattr(product, "good_comments_share", None))
        if good_rate_raw > 0 and good_rate_raw <= 1:
            good_rate_raw = good_rate_raw * 100
        good_rate = f"{good_rate_raw:.1f}%".rstrip("0").rstrip(".") if good_rate_raw > 0 else ""
        category = str(getattr(product, "category_name", "") or "").strip()
        shop = str(getattr(product, "shop_name", "") or "").strip()

        if sales_text:
            rows.append(("购买热度", sales_text))
        if comments > 0:
            rows.append(("用户评价", f"{comments // 10000}万+" if comments >= 10000 else f"{comments}+"))
        if good_rate:
            rows.append(("好评率", good_rate))
        if category:
            rows.append(("商品品类", category))
        if shop:
            rows.append(("店铺信息", shop))

        return "".join(
            f'<div class="kv"><span>{c(k)}</span><strong>{c(v)}</strong></div>'
            for k, v in rows
            if str(v).strip()
        )

    cards: list[str] = []
    for idx, product in enumerate(products, start=1):
        title = c(str(getattr(product, "title", "") or getattr(product, "sku_name", "") or "优选商品"))
        img = _product_pic_url(product)
        img_html = f'<img class="product-img" src="{c(img)}" alt="{title}" />' if img else ""
        card_slot = idx
        buy_url = _promotion_url(product, wechat_openid=wechat_openid, scene=scene_val, slot=card_slot)
        more_url = _more_like_this_url(product, scene=scene_val, slot=card_slot, wechat_openid=wechat_openid)
        price_main = c(_price_advantage_main(product))
        price_sub = c(_price_advantage_sub(product))
        reason = c(_commercial_reason(product))
        grid = info_rows(product)

        cards.append(f"""
        <div class="card">
          {img_html}
          <div class="title product-title">{title}</div>
          <div class="pricebox">
            <div class="price-main">{c(price_label)}：{price_main}</div>
            <div class="price-sub">{price_sub}</div>
          </div>
          <div class="section-title">{c(info_title)}</div>
          <div class="grid">{grid}</div>
          <div class="section-title">{c(reason_title)}</div>
          <div class="reason">{reason}</div>
          <div class="card-actions">
            <a class="btn btn-primary" href="{c(buy_url)}">{c(buy_text)}</a>
            <a class="btn btn-secondary" href="{c(more_url)}">{c(more_text)}</a>
          </div>
        </div>
        """.strip())

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>{c(page_title)}</title>
  <style>
    body{{margin:0;background:#f6f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f172a;}}
    .wrap{{max-width:760px;margin:0 auto;padding:16px 14px 40px;}}
    .page-title{{font-size:23px;font-weight:900;line-height:1.35;margin:2px 2px 16px;letter-spacing:-.2px;}}
    .card{{background:#fff;border-radius:20px;padding:16px;box-shadow:0 8px 28px rgba(15,23,42,.07);margin-bottom:14px;}}
    .title{{font-size:21px;font-weight:850;line-height:1.42;margin:0;letter-spacing:-.2px;}}
    .product-img{{width:100%;border-radius:18px;background:#fff;object-fit:cover;display:block;margin-bottom:12px;}}
    .product-title{{margin-bottom:10px;}}
    .pricebox{{margin-top:12px;padding:14px;border-radius:16px;background:#fff7ed;color:#9a3412;}}
    .price-main{{font-size:18px;font-weight:900;line-height:1.55;}}
    .price-sub{{margin-top:6px;font-size:13px;color:#9a3412;line-height:1.65;}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px;}}
    .kv{{background:#f8fafc;border-radius:14px;padding:10px;min-height:48px;}}
    .kv span{{display:block;color:#64748b;font-size:12px;line-height:1.4;}}
    .kv strong{{display:block;margin-top:4px;color:#0f172a;font-size:15px;line-height:1.4;word-break:break-word;}}
    .section-title{{font-size:16px;font-weight:850;margin:14px 0 8px;}}
    .reason{{color:#334155;line-height:1.85;font-size:15px;}}
    .card-actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;}}
    .btn{{display:block;text-align:center;padding:12px 14px;border-radius:14px;text-decoration:none;font-weight:850;font-size:15px;}}
    .btn-primary{{background:#0f172a;color:#fff;min-width:168px;}}
    .btn-secondary{{background:#e2e8f0;color:#0f172a;min-width:118px;}}
    @media (max-width:420px){{.grid{{grid-template-columns:1fr 1fr;gap:8px;}}.title{{font-size:19px;}}.page-title{{font-size:22px;}}.btn{{font-size:14px;padding:12px 10px;}}}}
  </style>
</head>
<body>
  <div class="wrap">
    <h1 class="page-title">{c(page_title)}</h1>
    {"".join(cards)}
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
    from app.services.wechat_find_product_entry_config_service import load_find_product_entry_config

    cfg = load_find_product_entry_config()
    more_cfg = cfg.get("h5_more_like_this") if isinstance(cfg.get("h5_more_like_this"), dict) else {}
    labels = more_cfg.get("labels") if isinstance(more_cfg.get("labels"), dict) else {}
    match_labels = more_cfg.get("match_reasons") if isinstance(more_cfg.get("match_reasons"), dict) else {}

    def c(value: object) -> str:
        return html.escape(html.unescape(str(value or "")), quote=True)

    def label(key: str, fallback: str = "") -> str:
        return str(labels.get(key) or fallback or key).strip()

    def cfg_text(key: str, fallback: str = "") -> str:
        return str(more_cfg.get(key) or fallback).strip()

    def first_attr(product: Product, *names: str) -> object:
        for name in names:
            value = getattr(product, name, None)
            if value not in (None, ""):
                return value
        return ""

    def image_url(product: Product) -> str:
        for key in ("image_url", "main_image_url", "image", "white_image"):
            val = str(getattr(product, key, "") or "").strip()
            if val:
                return val
        return ""

    def num_text(value: object) -> str:
        n = _to_int(value)
        if n <= 0:
            return ""
        if n >= 10000:
            return f"{n // 10000}万+"
        return f"{n}+"

    def rate_text(value: object) -> str:
        try:
            raw = float(value or 0)
        except Exception:
            return ""
        if raw <= 0:
            return ""
        if raw <= 1:
            raw = raw * 100
        return f"{raw:.1f}%".rstrip("0").rstrip(".")

    def safe_price_line(product: Product) -> tuple[str, str]:
        exact = bool(getattr(product, "is_exact_discount", False))
        purchase = _to_float(getattr(product, "purchase_price", None))
        basis = _to_float(getattr(product, "basis_price", None))
        saved = max(basis - purchase, 0.0) if basis > 0 and purchase > 0 else 0.0
        sales_line = num_text(first_attr(product, "sales_volume", "order_count_30d", "in_order_count_30_days", "monthly_sales"))
        sep = cfg_text("price_separator")

        if exact and purchase > 0 and basis > purchase:
            main = f"优惠价¥{purchase:g}｜立省¥{saved:g}"
            if sales_line:
                main = f"{main}｜{cfg_text('sales_prefix')}{sales_line}"
            return main, cfg_text("price_note_verified")

        fallback = cfg_text("fallback_price_line")
        if sales_line:
            return f"{cfg_text('sales_prefix')}{sales_line}{sep}{fallback}", cfg_text("price_note_realtime")
        return fallback, cfg_text("price_note_realtime")

    raw_stopwords = more_cfg.get("similar_stopwords")
    stopwords = {str(x).strip().lower() for x in raw_stopwords if str(x).strip()} if isinstance(raw_stopwords, list) else set()

    def norm_tokens(text: str) -> list[str]:
        raw = re.findall(r"[a-z0-9\u4e00-\u9fff]+", str(text or "").lower())
        out: list[str] = []
        for tok in raw:
            if tok.isdigit() or len(tok) < 2:
                continue
            if tok in stopwords:
                continue
            out.append(tok)
        return out

    def brand_tokens(product: Product) -> set[str]:
        out: set[str] = set()
        shop = _shop_key(product)
        if shop:
            out.add(shop)
        title = str(getattr(product, "title", "") or "")
        for tok in norm_tokens(title):
            out.add(tok)
            if len(out) >= 8:
                break
        return out

    def match_reason_text(*, same_shop: bool, same_brand: bool, same_cat: bool, same_use: bool) -> str:
        if same_shop:
            return str(match_labels.get("same_shop") or "")
        if same_brand:
            return str(match_labels.get("same_brand") or "")
        if same_cat:
            return str(match_labels.get("same_category") or "")
        if same_use:
            return str(match_labels.get("same_use") or "")
        return str(match_labels.get("fallback") or "")

    base_product = get_product_by_id(db, int(product_id))
    if not base_product:
        not_found_title = cfg_text("base_not_found_title")
        not_found_desc = cfg_text("base_not_found_desc")
        return _html_shell(
            not_found_title,
            f'<div class="card"><div class="title">{c(not_found_title)}</div><div class="meta">{c(not_found_desc)}</div></div>',
        )

    rows = [x for x in _active_recommend_products(db) if int(x.id) != int(product_id)]

    base_cat = _category_key(base_product)
    base_shop = _shop_key(base_product)
    base_brand = brand_tokens(base_product)
    base_tokens = set(norm_tokens(str(getattr(base_product, "title", "") or "")))

    scored: list[tuple[int, str, Product]] = []
    for x in rows:
        cand_cat = _category_key(x)
        cand_shop = _shop_key(x)
        cand_brand = brand_tokens(x)
        cand_tokens = set(norm_tokens(str(getattr(x, "title", "") or "")))

        same_shop = bool(base_shop and cand_shop and cand_shop == base_shop)
        same_brand = bool(base_brand and cand_brand and (base_brand & cand_brand))
        same_cat = bool(base_cat and cand_cat and cand_cat == base_cat)
        token_overlap = base_tokens & cand_tokens
        same_use = len(token_overlap) >= 2 or (same_cat and len(token_overlap) >= 1)

        if not (same_shop or same_brand or same_cat or same_use):
            continue

        score = 0
        if same_shop:
            score += 80
        if same_brand:
            score += 60
        if same_cat:
            score += 45
        if same_use:
            score += 35
        score += min(len(token_overlap), 5) * 8
        score += min(_to_int(getattr(x, "sales_volume", None)), 10000) // 1000

        reason = match_reason_text(
            same_shop=same_shop,
            same_brand=same_brand,
            same_cat=same_cat,
            same_use=same_use,
        )
        scored.append((score, reason, x))

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

    try:
        max_cards = int(more_cfg.get("max_cards") or 6)
    except Exception:
        max_cards = 6

    picked: list[tuple[str, Product]] = []
    seen_ids: set[int] = set()
    seen_titles: set[str] = set()
    for _, reason, x in scored:
        pid = int(x.id)
        titlek = _title_key(x)
        if pid in seen_ids or titlek in seen_titles:
            continue
        picked.append((reason, x))
        seen_ids.add(pid)
        seen_titles.add(titlek)
        if len(picked) >= max_cards:
            break

    scene_val = scene or "more_like_this"
    slot_base = _to_int(slot or 0)

    base_title = str(getattr(base_product, "title", "") or "")
    base_img = image_url(base_product)
    base_img_html = f'<img class="base-img" src="{c(base_img)}" alt="{c(base_title)}" />' if base_img else ""

    header = f"""
    <div class="card header-card">
      {base_img_html}
      <div>
        <div class="eyebrow">{c(cfg_text("base_prefix"))}</div>
        <div class="title">{c(base_title)}</div>
        <div class="meta">{c(cfg_text("intro"))}</div>
      </div>
    </div>
    """.strip()

    cards: list[str] = []
    for idx, pair in enumerate(picked, 1):
        match_reason, x = pair
        title = str(getattr(x, "title", "") or "")
        shop = str(first_attr(x, "shop_name", "merchant_name", "vendor_name") or "")
        category = str(first_attr(x, "category_name", "category", "cid_name") or "")
        sales = num_text(first_attr(x, "sales_volume", "order_count_30d", "in_order_count_30_days", "monthly_sales"))
        comments = num_text(first_attr(x, "comment_count", "comments_count", "review_count", "good_comments"))
        good_rate = rate_text(first_attr(x, "good_comment_rate", "good_comments_share", "positive_rate", "good_rate"))

        price_main, price_note = safe_price_line(x)
        reason = _recommend_reason_short(x)

        img = image_url(x)
        img_html = f'<img class="product-img" src="{c(img)}" alt="{c(title)}" />' if img else ""

        info_pairs = [
            (label("sales"), sales),
            (label("comments"), comments),
            (label("good_rate"), good_rate),
            (label("category"), category),
            (label("shop"), shop),
        ]
        info_html = "".join(
            f'<div class="kv"><span>{c(k)}</span><strong>{c(v)}</strong></div>'
            for k, v in info_pairs
            if str(v or "").strip()
        )

        buy_link = _promotion_url(
            x,
            wechat_openid=wechat_openid,
            scene=scene_val,
            slot=slot_base + idx,
        )
        detail_link = _detail_url(
            x,
            scene=scene_val,
            slot=slot_base + idx,
            wechat_openid=wechat_openid,
        )

        cards.append(
            f"""
            <div class="card product-card">
              {img_html}
              <div class="rank">{c(cfg_text("item_rank_prefix"))} {idx}</div>
              <div class="title product-title">{c(title)}</div>
              <div class="match"><strong>{c(label("match"))}：</strong>{c(match_reason)}</div>
              <div class="pricebox">
                <div class="price-main">{c(label("price"))}：{c(price_main)}</div>
                <div class="price-sub">{c(price_note)}</div>
              </div>
              <div class="grid">{info_html}</div>
              <div class="section-title">{c(label("reason"))}</div>
              <div class="reason">{c(reason)}</div>
              <div class="card-actions">
                <a class="btn btn-primary" href="{c(buy_link)}">{c(label("buy"))}</a>
                <a class="btn btn-secondary" href="{c(detail_link)}">{c(label("detail"))}</a>
              </div>
            </div>
            """.strip()
        )

    if cards:
        body = header + "\n" + "\n".join(cards)
    else:
        body = header + "\n" + f"""
        <div class="card">
          <div class="title">{c(cfg_text("empty_title"))}</div>
          <div class="meta">{c(cfg_text("empty_desc"))}</div>
        </div>
        """.strip()

    title = cfg_text("title")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>{c(title)}</title>
  <style>
    body{{margin:0;background:#f6f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f172a;}}
    .wrap{{max-width:760px;margin:0 auto;padding:14px 14px 32px;}}
    .card{{background:#fff;border-radius:20px;padding:16px;box-shadow:0 8px 28px rgba(15,23,42,.07);margin-bottom:14px;}}
    .header-card{{display:grid;grid-template-columns:88px 1fr;gap:12px;align-items:center;}}
    .base-img{{width:88px;height:88px;border-radius:16px;object-fit:cover;background:#fff;}}
    .eyebrow{{font-size:12px;color:#64748b;font-weight:800;margin-bottom:4px;}}
    .title{{font-size:20px;font-weight:850;line-height:1.42;margin:0;letter-spacing:-.2px;}}
    .meta{{margin-top:8px;color:#64748b;line-height:1.75;font-size:14px;}}
    .product-img{{width:100%;border-radius:18px;background:#fff;object-fit:cover;display:block;margin-bottom:12px;}}
    .rank{{display:inline-flex;margin-bottom:8px;padding:5px 9px;border-radius:999px;background:#eef2ff;color:#3730a3;font-size:12px;font-weight:850;}}
    .product-title{{margin-bottom:10px;}}
    .match{{background:#f8fafc;border-radius:14px;padding:10px;color:#334155;line-height:1.7;font-size:14px;}}
    .pricebox{{margin-top:12px;padding:14px;border-radius:16px;background:#fff7ed;color:#9a3412;}}
    .price-main{{font-size:18px;font-weight:900;line-height:1.5;}}
    .price-sub{{margin-top:6px;font-size:13px;color:#9a3412;line-height:1.65;}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px;}}
    .kv{{background:#f8fafc;border-radius:14px;padding:10px;min-height:48px;}}
    .kv span{{display:block;color:#64748b;font-size:12px;line-height:1.4;}}
    .kv strong{{display:block;margin-top:4px;color:#0f172a;font-size:15px;line-height:1.4;word-break:break-word;}}
    .section-title{{font-size:15px;font-weight:850;margin:14px 0 8px;}}
    .reason{{color:#334155;line-height:1.85;font-size:15px;}}
    .card-actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;}}
    .btn{{display:block;text-align:center;padding:12px 14px;border-radius:14px;text-decoration:none;font-weight:850;font-size:14px;}}
    .btn-primary{{background:#0f172a;color:#fff;flex:1 1 180px;}}
    .btn-secondary{{background:#e2e8f0;color:#0f172a;flex:1 1 120px;}}
    @media (max-width:420px){{.header-card{{grid-template-columns:76px 1fr;}}.base-img{{width:76px;height:76px;}}.grid{{grid-template-columns:1fr 1fr;gap:8px;}}.title{{font-size:18px;}}}}
  </style>
</head>
<body>
  <div class="wrap">
    {body}
  </div>
</body>
</html>"""

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
