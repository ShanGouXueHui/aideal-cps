from __future__ import annotations

import hashlib
import html
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.wechat_recommend_config import (
    FIND_HINT,
    FLAGSHIP_KEYWORDS,
    LABEL_DETAIL,
    LABEL_JD,
    LABEL_PRICE,
    LABEL_REASON,
    TITLE_PREFIX_FIND,
    TITLE_PREFIX_TODAY,
    TODAY_EMPTY_HINT,
    TODAY_NEXT_HINT,
    TODAY_RECOMMEND_BATCH_SIZE,
    TODAY_RECOMMEND_DEDUP_DAYS,
    TODAY_RECOMMEND_FALLBACK_ENABLED,
    TODAY_RECOMMEND_FALLBACK_LIMIT,
    TODAY_RECOMMEND_SCENE,
    PRICE_REFRESH_BEFORE_RECOMMEND_ENABLED,
    PRICE_REFRESH_MAX_AGE_MINUTES,
)
from app.models.product import Product
from app.models.wechat_recommend_exposure import WechatRecommendExposure
from app.services.catalog_refresh_config_service import load_catalog_refresh_rules
from app.services.catalog_refresh_service import (
    _product_payload_from_live_row,
    refresh_elite_catalogs,
    refresh_keyword_catalog,
)
from app.services.jd_live_search_service import search_live_jd_products
from app.services.jd_product_sync_service import upsert_product
from app.services.jd_exact_price_service import refresh_single_product_exact_price
from app.services.product_compliance_service import evaluate_product_instance
from app.services.recommendation_guard_service import allow_proactive_recommend


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "https://aidealfy.kindafeelfy.cn"


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value not in (None, ""):
        return str(value).strip()
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            if key.strip() == name:
                return val.strip().strip('"').strip("'")
    return default


def _base_url() -> str:
    return (_env("WECHAT_H5_BASE_URL") or _env("PUBLIC_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _safe_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _openid_key(openid: str) -> str:
    return hashlib.sha1(openid.encode("utf-8")).hexdigest()[:24]


def _normalize_dt(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _has_fresh_price(product: Product) -> bool:
    last_sync_at = _normalize_dt(getattr(product, "last_sync_at", None))
    if last_sync_at is None:
        return False
    age = datetime.now(timezone.utc) - last_sync_at
    return age <= timedelta(minutes=PRICE_REFRESH_MAX_AGE_MINUTES)


def _price_snapshot(product: Product) -> dict[str, Any]:
    fresh = _has_fresh_price(product)
    official_price = _safe_decimal(getattr(product, "price", 0))
    coupon_price = _safe_decimal(getattr(product, "coupon_price", 0))

    if not fresh:
        return {
            "fresh": False,
            "official_price": Decimal("0"),
            "final_price": Decimal("0"),
            "saved": Decimal("0"),
        }

    if official_price <= 0 and coupon_price <= 0:
        return {
            "fresh": False,
            "official_price": Decimal("0"),
            "final_price": Decimal("0"),
            "saved": Decimal("0"),
        }

    final_price = coupon_price if coupon_price > 0 and (official_price <= 0 or coupon_price <= official_price) else official_price
    saved = official_price - final_price if official_price > 0 and final_price > 0 and official_price > final_price else Decimal("0")

    return {
        "fresh": True,
        "official_price": official_price,
        "final_price": final_price,
        "saved": saved,
    }


def _price_text(product: Product) -> str:
    snap = _price_snapshot(product)
    final_price = snap["discount_price"]

    if snap["fresh"] and final_price > 0:
        return f"优惠价¥{final_price:.2f}（以下单页实时为准）"

    return "优惠价以下单页实时信息为准，先到先得。"
def _saved_text(product: Product) -> str:
    snap = _price_snapshot(product)
    if snap["fresh"] and snap["discount_price"] > 0:
        return "价格和活动变化较快，以下单页实时信息为准，先到先得。"
    return "价格以下单页实时信息为准，先到先得。"
def _shop_name(product: Product) -> str:
    return str(getattr(product, "shop_name", "") or "").strip()



def _norm_token(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(value or "").strip().lower())


def _category_key(product: Product) -> str:
    return _norm_token(getattr(product, "category_name", "") or "")


def _brand_key(product: Product) -> str:
    title = str(getattr(product, "title", "") or "").strip()
    match = re.match(r"^([^\s（(【\[]+)", title)
    if match:
        token = _norm_token(match.group(1))
        if token:
            return token[:24]

    shop_name = _shop_name(product)
    shop_name = re.sub(r"(官方旗舰店|旗舰店|官方店|专卖店|专营店|京东自营|自营店|自营)$", "", shop_name)
    token = _norm_token(shop_name)
    return token[:24] if token else ""


def _similarity_key(product: Product) -> str:
    brand = _brand_key(product)
    category = _category_key(product)
    if brand and category:
        return f"{brand}|{category}"
    return brand or category or str(getattr(product, "jd_sku_id", "") or getattr(product, "id", "") or "")


def _recent_exposed_signature_sets(
    db: Session,
    *,
    openid_hash: str,
    dedup_days: int,
) -> tuple[set[str], set[str], set[str]]:
    since_at = datetime.now(timezone.utc) - timedelta(days=dedup_days)
    rows = (
        db.query(Product)
        .join(WechatRecommendExposure, Product.id == WechatRecommendExposure.product_id)
        .filter(
            WechatRecommendExposure.openid_hash == openid_hash,
            WechatRecommendExposure.created_at >= since_at,
        )
        .all()
    )

    category_keys: set[str] = set()
    brand_keys: set[str] = set()
    similarity_keys: set[str] = set()

    for row in rows:
        category_key = _category_key(row)
        brand_key = _brand_key(row)
        similarity_key = _similarity_key(row)

        if category_key:
            category_keys.add(category_key)
        if brand_key:
            brand_keys.add(brand_key)
        if similarity_key:
            similarity_keys.add(similarity_key)

    return category_keys, brand_keys, similarity_keys


def _owner_text(product: Product) -> str:
    owner = str(getattr(product, "owner", "") or "").strip().lower()
    if owner == "g":
        return "京东自营"
    shop_name = _shop_name(product)
    return shop_name or "店铺信息待补充"


def _is_flagship_shop(product: Product) -> bool:
    owner = str(getattr(product, "owner", "") or "").strip().lower()
    if owner == "g":
        return True
    shop_name = _shop_name(product)
    return any(keyword in shop_name for keyword in FLAGSHIP_KEYWORDS)


def _flagship_text(product: Product) -> str:
    if str(getattr(product, "owner", "") or "").strip().lower() == "g":
        return "京东自营，履约和售后更稳"
    shop_name = _shop_name(product)
    if shop_name and _is_flagship_shop(product):
        return f"{shop_name}出品，店铺资质更稳"
    return ""


def _first_attr(product: Product, names: list[str]):
    for name in names:
        value = getattr(product, name, None)
        if value not in (None, "", 0, 0.0):
            return value
    return None


def _comment_summary(product: Product) -> str:
    good_rate_value = _first_attr(product, [
        "good_rate",
        "good_comment_rate",
        "praise_rate",
        "positive_rate",
        "comment_good_rate",
    ])
    comment_count_value = _first_attr(product, [
        "comment_count",
        "comment_count",
        "review_count",
        "evaluate_count",
        "comment_num",
    ])
    five_star_count_value = _first_attr(product, [
        "five_star_count",
        "star5_count",
        "five_star_comment_count",
    ])

    parts: list[str] = []

    if good_rate_value is not None:
        rate = _safe_float(good_rate_value)
        if 0 < rate <= 1:
            rate = rate * 100
        if rate > 0:
            parts.append(f"好评率{rate:.1f}%")

    if comment_count_value is not None:
        count = _safe_int(comment_count_value)
        if count > 0:
            parts.append(f"评价{count}条")

    if five_star_count_value is not None:
        count = _safe_int(five_star_count_value)
        if count > 0:
            parts.append(f"五星{count}条")

    return "｜".join(parts[:3])


def _reason(product: Product) -> str:
    title = str(getattr(product, "title", "") or "")
    category_name = str(getattr(product, "category_name", "") or "")
    text = f"{title} {category_name}"

    low_decision_keywords = [
        "抽纸", "卷纸", "纸巾", "卫生纸", "湿巾", "洗衣液", "洗衣凝珠",
        "牙膏", "牙刷", "饮料", "牛奶", "面粉", "大米", "食用油",
        "垃圾袋", "保鲜膜", "洗洁精", "洗发水", "沐浴露",
    ]
    learning_keywords = [
        "练习册", "教辅", "压轴题", "阅读", "英语", "数学", "语文",
    ]

    if any(keyword in text for keyword in low_decision_keywords):
        return "这类商品更适合直接补货，核心价值是减少反复筛选和比价时间。"

    if any(keyword in text for keyword in learning_keywords):
        return "这类商品标准化程度较高，适合先看实时页面再快速完成决策。"

    return "先把高频对比动作省掉，点开看实时页面即可判断是否值得下单。"
def _direct_url(product: Product) -> str:
    for name in ["short_url", "product_url", "material_url"]:
        value = str(getattr(product, name, "") or "").strip()
        if value:
            return value
    return ""


def _h5_url(product: Product, *, scene: str, slot: int) -> str:
    return f"{_base_url()}/api/h5/recommend/{int(product.id)}?scene={scene}&slot={slot}"



def _today_rank_score(product: Product) -> float:
    return _weighted_score_product(product, _WECHAT_RECOMMEND_RULES)


def _today_product_rows(db: Session) -> list[Product]:
    pool_rules = (_WECHAT_RECOMMEND_RULES.get("pool_filters") or {})
    require_exact_discount = bool(pool_rules.get("require_exact_discount", True))
    require_basis_price_type = int(pool_rules.get("require_basis_price_type", 1))
    require_short_url = bool(pool_rules.get("require_short_url", True))
    require_merchant_recommendable = bool(pool_rules.get("require_merchant_recommendable", True))
    min_good_comments_share = float(pool_rules.get("min_good_comments_share", 95))
    min_comment_count = int(pool_rules.get("min_comment_count", 500))
    min_exact_delta = float(pool_rules.get("min_exact_delta", 5))
    exclude_title_keywords = [str(x).strip() for x in (pool_rules.get("exclude_title_keywords") or []) if str(x).strip()]

    query = (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.compliance_level == "normal",
            Product.allow_proactive_push == True,
        )
    )

    if require_exact_discount:
        query = query.filter(Product.is_exact_discount == True)

    if require_basis_price_type:
        query = query.filter(Product.basis_price_type == require_basis_price_type)

    if require_short_url:
        query = query.filter(Product.short_url.isnot(None), Product.short_url != "")

    if require_merchant_recommendable:
        query = query.filter(Product.merchant_recommendable == True)

    query = query.filter(
        Product.purchase_price.isnot(None),
        Product.basis_price.isnot(None),
        Product.purchase_price < Product.basis_price,
        Product.good_comments_share.isnot(None),
        Product.good_comments_share >= min_good_comments_share,
        Product.comment_count.isnot(None),
        Product.comment_count >= min_comment_count,
    )

    rows = query.all()

    filtered_rows = _filter_weighted_candidates(rows, _WECHAT_RECOMMEND_RULES)

    filtered_rows.sort(
        key=lambda row: (
            _today_rank_score(row),
            float((row.basis_price - row.purchase_price) if (row.basis_price is not None and row.purchase_price is not None) else 0),
            int(row.sales_volume or 0),
            int(row.comment_count or 0),
            float(row.good_comments_share or 0),
            float(row.estimated_commission or 0),
            int(row.id or 0),
        ),
        reverse=True,
    )

    filtered_rows = _reorder_with_diversity(filtered_rows, _WECHAT_RECOMMEND_RULES)
    return filtered_rows


def _recent_exposed_product_ids(
    db: Session,
    *,
    openid_hash: str,
    scene: str,
    dedup_days: int,
) -> set[int]:
    since_at = datetime.now(timezone.utc) - timedelta(days=dedup_days)
    rows = (
        db.query(WechatRecommendExposure.product_id)
        .filter(
            WechatRecommendExposure.openid_hash == openid_hash,
            WechatRecommendExposure.scene == scene,
            WechatRecommendExposure.created_at >= since_at,
        )
        .all()
    )
    return {int(row[0]) for row in rows if row and row[0] is not None}


def _record_exposures(
    db: Session,
    *,
    openid_hash: str,
    scene: str,
    products: list[Product],
) -> None:
    if not products:
        return
    rows = [
        WechatRecommendExposure(
            openid_hash=openid_hash,
            scene=scene,
            product_id=int(product.id),
        )
        for product in products
        if getattr(product, "id", None) is not None
    ]
    if not rows:
        return
    db.add_all(rows)
    db.commit()


def _refresh_product_from_jd_live(db: Session, product: Product) -> Product:
    if not PRICE_REFRESH_BEFORE_RECOMMEND_ENABLED:
        return product
    if not getattr(product, "jd_sku_id", None) or not getattr(product, "title", None):
        return product

    try:
        product = refresh_single_product_exact_price(db, product)
        rows = search_live_jd_products(query_text=str(product.title).strip(), limit=10)
        target = None
        for row in rows:
            if str(row.get("jd_sku_id") or "") == str(product.jd_sku_id):
                target = row
                break

        if not target:
            return product

        field_names = [
            "title",
            "image_url",
            "material_url",
            "short_url",
            "product_url",
            "category_name",
            "shop_name",
            "shop_id",
            "price",
            "coupon_price",
            "commission_rate",
            "estimated_commission",
            "sales_volume",
            "owner",
            "merchant_health_score",
            "merchant_recommendable",
            "compliance_level",
            "age_gate_required",
            "allow_proactive_push",
            "allow_partner_share",
            "compliance_notes",
            "reason",
        ]
        for key in field_names:
            if key in target and target.get(key) is not None:
                if key == "reason":
                    setattr(product, "ai_reason", target.get(key))
                elif hasattr(product, key):
                    setattr(product, key, target.get(key))

        product.last_sync_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(product)
    except Exception:
        db.rollback()

    return product


def _refresh_products_before_recommend(db: Session, products: list[Product]) -> list[Product]:
    return [_refresh_product_from_jd_live(db, product) for product in products]


def _refill_today_pool_from_jd(db: Session) -> None:
    if not TODAY_RECOMMEND_FALLBACK_ENABLED:
        return

    rules = load_catalog_refresh_rules()
    keywords = list(rules.get("keyword_seeds", []))
    keyword_limit = max(int(rules.get("keyword_sync_limit", 12)), TODAY_RECOMMEND_FALLBACK_LIMIT)
    elite_limit = max(int(rules.get("elite_sync_limit", 20)), TODAY_RECOMMEND_FALLBACK_LIMIT)

    for keyword in keywords:
        try:
            refresh_keyword_catalog(db, keyword=keyword, limit=keyword_limit, with_short_links=False)
        except Exception:
            db.rollback()

    try:
        refresh_elite_catalogs(db, limit=elite_limit, with_short_links=False)
    except Exception:
        db.rollback()

    for keyword in keywords:
        try:
            rows = search_live_jd_products(query_text=keyword, limit=keyword_limit)
            for row in rows:
                payload = _product_payload_from_live_row(row, keyword=keyword)
                upsert_product(db, payload)
            db.commit()
        except Exception:
            db.rollback()


def _select_today_batch(
    db: Session,
    *,
    wechat_openid: str,
) -> list[Product]:
    openid_hash = _openid_key(wechat_openid)

    def unseen_rows() -> list[Product]:
        rows = _today_product_rows(db)
        recent_ids = _recent_exposed_product_ids(
            db,
            openid_hash=openid_hash,
            scene=TODAY_RECOMMEND_SCENE,
            dedup_days=TODAY_RECOMMEND_DEDUP_DAYS,
        )
        recent_category_keys, recent_brand_keys, recent_similarity_keys = _recent_exposed_signature_sets(
            db,
            openid_hash=openid_hash,
            dedup_days=TODAY_RECOMMEND_DEDUP_DAYS,
        )

        filtered: list[Product] = []
        for row in rows:
            row_id = int(getattr(row, "id", 0) or 0)
            category_key = _category_key(row)
            brand_key = _brand_key(row)
            similarity_key = _similarity_key(row)

            if row_id in recent_ids:
                continue
            if similarity_key and similarity_key in recent_similarity_keys:
                continue
            if category_key and category_key in recent_category_keys:
                continue
            if brand_key and brand_key in recent_brand_keys:
                continue

            filtered.append(row)

        return filtered

    candidates = unseen_rows()

    if len(candidates) < TODAY_RECOMMEND_BATCH_SIZE:
        _refill_today_pool_from_jd(db)
        candidates = unseen_rows()

    strict_selected: list[Product] = []
    strict_selected_ids: set[int] = set()
    seen_categories: set[str] = set()
    seen_brands: set[str] = set()
    seen_similarities: set[str] = set()

    for row in candidates:
        row_id = int(getattr(row, "id", 0) or 0)
        category_key = _category_key(row)
        brand_key = _brand_key(row)
        similarity_key = _similarity_key(row)

        if similarity_key and similarity_key in seen_similarities:
            continue
        if category_key and category_key in seen_categories:
            continue
        if brand_key and brand_key in seen_brands:
            continue

        strict_selected.append(row)
        strict_selected_ids.add(row_id)

        if similarity_key:
            seen_similarities.add(similarity_key)
        if category_key:
            seen_categories.add(category_key)
        if brand_key:
            seen_brands.add(brand_key)

        if len(strict_selected) >= TODAY_RECOMMEND_BATCH_SIZE:
            break

    if len(strict_selected) < TODAY_RECOMMEND_BATCH_SIZE:
        for row in candidates:
            row_id = int(getattr(row, "id", 0) or 0)
            similarity_key = _similarity_key(row)
            if row_id in strict_selected_ids:
                continue
            if similarity_key and similarity_key in seen_similarities:
                continue
            strict_selected.append(row)
            strict_selected_ids.add(row_id)
            if similarity_key:
                seen_similarities.add(similarity_key)
            if len(strict_selected) >= TODAY_RECOMMEND_BATCH_SIZE:
                break

    batch = strict_selected[:TODAY_RECOMMEND_BATCH_SIZE]
    if not batch:
        return []

    batch = _refresh_products_before_recommend(db, batch)

    _record_exposures(
        db,
        openid_hash=openid_hash,
        scene=TODAY_RECOMMEND_SCENE,
        products=batch,
    )
    return batch


def _today_text(products: list[Product]) -> str:
    lines = [TITLE_PREFIX_TODAY, ""]
    for idx, product in enumerate(products, start=1):
        lines.append(f"【{idx}】{str(getattr(product, 'title', '') or '商品').strip()}")
        lines.append(f"{LABEL_PRICE}：{_price_text(product)}")
        lines.append(f"{LABEL_REASON}：{_reason(product)}")
        lines.append(f"{LABEL_DETAIL}：{_h5_url(product, scene=TODAY_RECOMMEND_SCENE, slot=idx)}")
        lines.append(f"{LABEL_JD}：{_direct_url(product)}")
        lines.append("")
    lines.append(TODAY_NEXT_HINT)
    return "\n".join(lines).strip()


def _find_text(product: Product) -> str:
    return "\n".join([
        TITLE_PREFIX_FIND,
        f"{str(getattr(product, 'title', '') or '商品').strip()}",
        f"{LABEL_PRICE}：{_price_text(product)}",
        f"{LABEL_REASON}：{_reason(product)}",
        f"{LABEL_DETAIL}：{_h5_url(product, scene='find_product_entry', slot=1)}",
        f"{LABEL_JD}：{_direct_url(product)}",
        "",
        FIND_HINT,
    ]).strip()


def get_today_recommend_text_reply(db: Session, wechat_openid: str) -> str | None:
    batch = _select_today_batch(db, wechat_openid=wechat_openid)
    if not batch:
        return TODAY_EMPTY_HINT
    return _today_text(batch)


def get_find_product_entry_text_reply(db: Session, wechat_openid: str) -> str | None:
    product = _find_entry_product(db, wechat_openid=wechat_openid)
    if not product:
        return None
    product = _refresh_product_from_jd_live(db, product)
    _record_exposures(
        db,
        openid_hash=_openid_key(wechat_openid),
        scene="find_product_entry",
        products=[product],
    )
    return _find_text(product)


def get_product_by_id(db: Session, product_id: int) -> Product | None:
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return None
    return _refresh_product_from_jd_live(db, product)


def render_product_h5(product: Product, *, scene: str = "", slot: str = "") -> str:
    title = html.escape(str(getattr(product, "title", "") or "智省优选推荐"))
    image_url = html.escape(str(getattr(product, "image_url", "") or "").strip(), quote=True)
    price_text = html.escape(_price_text(product))
    saved_text_raw = _saved_text(product)
    saved_text = html.escape(saved_text_raw or "价格以下单页实时为准，先到先得。")
    sales_volume = _safe_int(getattr(product, "sales_volume", 0))
    owner_text = html.escape(_owner_text(product))
    flagship_text = html.escape(_flagship_text(product))
    comment_text = html.escape(_comment_summary(product))
    category_name = html.escape(str(getattr(product, "category_name", "") or "").strip() or "京东好物")
    reason_text = html.escape(_h5_reason(product))
    jd_url = html.escape(_direct_url(product), quote=True)

    sales_line = f"已售 {sales_volume} 件" if sales_volume > 0 else "销量信息以京东页为准"

    quality_line = flagship_text or owner_text
    if comment_text:
        quality_line = f"{quality_line}｜{comment_text}" if quality_line else comment_text

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{title}</title>
  <style>
    *{{box-sizing:border-box;}}
    body{{margin:0;background:#f5f7fb;color:#111827;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",Arial,sans-serif;}}
    .wrap{{max-width:760px;margin:0 auto;padding:16px 16px 40px;}}
    .card{{background:#fff;border-radius:20px;overflow:hidden;box-shadow:0 8px 28px rgba(15,23,42,.08);}}
    .hero{{width:100%;display:block;background:#fff;}}
    .content{{padding:18px;}}
    .badge{{display:inline-block;background:#e8fff0;color:#067647;border-radius:999px;padding:6px 12px;font-size:13px;font-weight:700;}}
    h1{{font-size:22px;line-height:1.45;margin:14px 0 10px;}}
    .price{{font-size:28px;font-weight:800;color:#dc2626;margin:8px 0;line-height:1.5;}}
    .sub{{font-size:14px;color:#6b7280;line-height:1.7;}}
    .reason{{margin-top:14px;background:#f8fafc;border-radius:14px;padding:14px 14px 2px;}}
    .reason h2{{font-size:16px;margin:0 0 8px;}}
    .reason p{{margin:0 0 12px;line-height:1.75;color:#334155;}}
    .meta{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px;}}
    .meta .item{{background:#f8fafc;border-radius:14px;padding:12px;}}
    .meta .k{{font-size:12px;color:#6b7280;}}
    .meta .v{{font-size:15px;font-weight:700;margin-top:6px;line-height:1.5;}}
    .cta{{position:sticky;bottom:0;left:0;right:0;background:linear-gradient(to top, rgba(245,247,251,1), rgba(245,247,251,.92), rgba(245,247,251,0));padding-top:18px;margin-top:18px;}}
    .btn{{display:block;width:100%;text-align:center;background:#1f3d36;color:#fff;text-decoration:none;border-radius:14px;padding:16px 18px;font-size:17px;font-weight:800;}}
    .tip{{margin-top:10px;font-size:12px;color:#6b7280;line-height:1.6;text-align:center;}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <img class="hero" src="{image_url}" alt="{title}">
      <div class="content">
        <div class="badge">{category_name}</div>
        <h1>{title}</h1>
        <div class="price">{price_text}</div>
        <div class="sub">{saved_text}</div>

        <div class="reason">
          <h2>为什么推荐</h2>
          <p>{reason_text}</p>
        </div>

        <div class="meta">
          <div class="item">
            <div class="k">品质 / 店铺</div>
            <div class="v">{quality_line or "以京东页展示为准"}</div>
          </div>
          <div class="item">
            <div class="k">热度</div>
            <div class="v">{html.escape(sales_line)}</div>
          </div>
        </div>

        <div class="cta">
          <a class="btn" href="{jd_url}">去京东购买</a>
          <div class="tip">价格、评价与库存以下单页实时信息为准，先到先得。</div>
        </div>
      </div>
    </div>
  </div>
</body>
</html>"""


# === exact price / copy override ===
from app.services.recommend_price_copy_service import (
    price_snapshot as _exact_price_snapshot,
    price_text as _exact_price_text,
    h5_reason as _exact_h5_reason,
)

from app.services.recommend_price_copy_config_service import load_recommend_price_copy_rules
from app.services.wechat_recommend_rules_config_service import load_wechat_recommend_rules
from app.services.wechat_recommend_ranking_service import (
    score_product as _weighted_score_product,
    filter_candidates as _filter_weighted_candidates,
    reorder_with_diversity as _reorder_with_diversity,
    select_batch_with_diversity as _select_batch_with_diversity,
)

_COPY_RULES = load_recommend_price_copy_rules()
_WECHAT_RECOMMEND_RULES = load_wechat_recommend_rules()
LABEL_PRICE = _COPY_RULES.get("labels", {}).get("price", "优惠价")

_ORIG_REFRESH_PRODUCT_FROM_JD_LIVE = _refresh_product_from_jd_live

def _price_snapshot(product: Product) -> dict[str, Any]:
    return _exact_price_snapshot(product)

def _price_text(product: Product) -> str:
    return _exact_price_text(product)

def _h5_reason(product: Product) -> str:
    return _exact_h5_reason(product)

def _refresh_product_from_jd_live(db: Session, product: Product) -> Product:
    if bool(getattr(product, "is_exact_discount", False)) and getattr(product, "price_verified_at", None):
        return product
    return _ORIG_REFRESH_PRODUCT_FROM_JD_LIVE(db, product)

# --- compatibility exports for message_router ---
def has_today_recommend_products(db):
    row = (
        db.query(Product.id)
        .filter(
            Product.status == "active",
            Product.allow_proactive_push.is_(True),
            Product.short_url.isnot(None),
            Product.short_url != "",
        )
        .order_by(Product.updated_at.desc(), Product.id.desc())
        .first()
    )
    return row is not None

def has_find_entry_product(db):
    return has_today_recommend_products(db)


# >>> STABLE_CYCLE_OVERRIDE_BEGIN >>>
from decimal import Decimal as _StableDecimal

def _stable_cfg_label(name: str, default: str) -> str:
    try:
        return str((((_WECHAT_RECOMMEND_RULES or {}).get("labels") or {}).get(name)) or default)
    except Exception:
        return default

LABEL_BUY = _stable_cfg_label("buy", "下单链接")

def _stable_promotion_redirect_url(product, *, wechat_openid: str, scene: str, slot: int) -> str:
    rules = _WECHAT_RECOMMEND_RULES or {}
    url_cfg = rules.get("url_templates") or rules.get("url") or {}
    tpl = str(
        url_cfg.get("promotion_redirect_path_template")
        or "/api/promotion/redirect?wechat_openid={wechat_openid}&product_id={product_id}&scene={scene}&slot={slot}"
    ).strip()
    if not tpl.startswith("/"):
        tpl = "/" + tpl
    return _base_url().rstrip("/") + tpl.format(
        wechat_openid=wechat_openid,
        product_id=int(getattr(product, "id")),
        scene=scene,
        slot=slot,
    )

def _stable_to_decimal(value):
    try:
        if value is None or value == "":
            return None
        return _StableDecimal(str(value))
    except Exception:
        return None

def _stable_to_int(value, default=0):
    try:
        return int(value or 0)
    except Exception:
        return default

def _stable_to_float(value, default=0.0):
    try:
        return float(value or 0.0)
    except Exception:
        return default

def _stable_price_text(product) -> str:
    purchase_price = _stable_to_decimal(getattr(product, "purchase_price", None))
    basis_price = _stable_to_decimal(getattr(product, "basis_price", None))
    coupon_price = _stable_to_decimal(getattr(product, "coupon_price", None))
    price = _stable_to_decimal(getattr(product, "price", None))

    if (
        purchase_price is not None
        and basis_price is not None
        and purchase_price > 0
        and basis_price > 0
        and purchase_price < basis_price
    ):
        delta = basis_price - purchase_price
        return f"优惠价￥{purchase_price:.2f}｜京东官网价￥{basis_price:.2f}｜立省￥{delta:.2f}"

    final_price = coupon_price if coupon_price is not None and coupon_price > 0 else price
    ref_price = price if price is not None and price > 0 else None
    if final_price is not None and ref_price is not None and final_price < ref_price:
        delta = ref_price - final_price
        return f"优惠价￥{final_price:.2f}｜标价￥{ref_price:.2f}｜立省￥{delta:.2f}"
    if final_price is not None and final_price > 0:
        return f"到手参考￥{final_price:.2f}"
    return "以下单页实时信息为准"

def _stable_reason(product) -> str:
    sales_volume = _stable_to_int(getattr(product, "sales_volume", None))
    good_comments_share = _stable_to_float(getattr(product, "good_comments_share", None))
    comment_count = _stable_to_int(getattr(product, "comment_count", None))

    purchase_price = _stable_to_decimal(getattr(product, "purchase_price", None))
    basis_price = _stable_to_decimal(getattr(product, "basis_price", None))
    if (
        purchase_price is not None
        and basis_price is not None
        and purchase_price > 0
        and basis_price > 0
        and purchase_price < basis_price
    ):
        discount_rate = float((basis_price - purchase_price) / basis_price)
    else:
        discount_rate = 0.0

    if sales_volume >= 500:
        return "近期成交更扎实，属于更适合优先下单验证的一类。"
    if comment_count >= 20000 and good_comments_share >= 95:
        return "评论沉淀更充分，口碑稳定性更高，决策成本更低。"
    if discount_rate >= 0.30 and comment_count >= 5000:
        return "当前价差已经明显拉开，同时评论基数不低，适合先看实时页面。"
    if good_comments_share >= 98 and comment_count >= 5000:
        return "好评率和评论量都更稳，属于更省心的一档。"
    return "价格、销量和口碑已经过一轮筛选，适合先看实时页面再决定。"

def _stable_cycle_rows(db, *, scene: str, openid_hash: str, rows, batch_size: int):
    rows = list(rows or [])
    if not rows:
        return []

    current_ids = [int(getattr(row, "id")) for row in rows if getattr(row, "id", None) is not None]
    if not current_ids:
        return rows[:batch_size]

    exposure_rows = (
        db.query(WechatRecommendExposure.product_id)
        .filter(
            WechatRecommendExposure.openid_hash == openid_hash,
            WechatRecommendExposure.scene == scene,
            WechatRecommendExposure.product_id.in_(current_ids),
        )
        .order_by(WechatRecommendExposure.id.asc())
        .all()
    )
    exposed_ids = {int(row[0]) for row in exposure_rows if row and row[0] is not None}
    remaining = [row for row in rows if int(getattr(row, "id")) not in exposed_ids]
    if remaining:
        return remaining[:batch_size]
    return rows[:batch_size]

def _select_today_batch(db, *, wechat_openid: str):
    rows = list(_today_product_rows(db) or [])
    openid_hash = _openid_key(wechat_openid)
    batch_size = max(1, _stable_to_int(globals().get("TODAY_RECOMMEND_BATCH_SIZE", 3), 3))
    return _stable_cycle_rows(
        db,
        scene=TODAY_RECOMMEND_SCENE,
        openid_hash=openid_hash,
        rows=rows,
        batch_size=batch_size,
    )

def _find_entry_product(db, *, wechat_openid: str):
    rows = list(_today_product_rows(db) or [])
    openid_hash = _openid_key(wechat_openid)
    picked = _stable_cycle_rows(
        db,
        scene="find_product_entry",
        openid_hash=openid_hash,
        rows=rows,
        batch_size=1,
    )
    return picked[0] if picked else None

def has_today_recommend_products(*args, **kwargs):
    db = None
    if args:
        db = args[0]
    if db is None:
        db = kwargs.get("db") or kwargs.get("session")
    if db is None:
        return False
    try:
        return bool(_today_product_rows(db))
    except Exception:
        return False

def has_find_entry_product(*args, **kwargs) -> bool:
    db = None
    if args:
        db = args[0]
    if db is None:
        db = kwargs.get("db") or kwargs.get("session")
    if db is None:
        return False
    try:
        return _find_entry_product(db, wechat_openid="compat_check_openid") is not None
    except Exception:
        return False

def get_today_recommend_text_reply(db, wechat_openid: str):
    batch = _select_today_batch(db, wechat_openid=wechat_openid)
    if not batch:
        return globals().get("TODAY_EMPTY_HINT") or "当前还没有合适的商品，稍后再来。"

    openid_hash = _openid_key(wechat_openid)
    _record_exposures(
        db,
        openid_hash=openid_hash,
        scene=TODAY_RECOMMEND_SCENE,
        products=batch,
    )

    lines = [f"今天先给你挑 {len(batch)} 个当前商品池里更稳、更值的商品：", ""]
    for idx, product in enumerate(batch, 1):
        title = str(getattr(product, "title", "") or "").strip()
        shop_name = str(getattr(product, "shop_name", "") or "以页面为准").strip()
        lines.extend(
            [
                f"{idx}.",
                title,
                f"到手参考：{_stable_price_text(product)}",
                f"店铺：{shop_name}",
                f"理由：{_stable_reason(product)}",
                f"{LABEL_BUY}：{_stable_promotion_redirect_url(product, wechat_openid=wechat_openid, scene=TODAY_RECOMMEND_SCENE, slot=idx)}",
                "",
            ]
        )

    batch_size = max(1, _stable_to_int(globals().get("TODAY_RECOMMEND_BATCH_SIZE", 3), 3))
    if len(batch) >= batch_size:
        lines.append("再点一次“今日推荐”，继续下一组。")
    else:
        lines.append("当前池这一轮先看到这里；再点一次“今日推荐”，会从头轮转。")
    return "\n".join(lines).strip()

def get_find_product_entry_text_reply(db, wechat_openid: str):
    product = _find_entry_product(db, wechat_openid=wechat_openid)
    if not product:
        return globals().get("FIND_HINT") or "你可以直接回复想买的商品，比如：卫生纸、洗衣液、宝宝湿巾。"

    _record_exposures(
        db,
        openid_hash=_openid_key(wechat_openid),
        scene="find_product_entry",
        products=[product],
    )

    title = str(getattr(product, "title", "") or "").strip()
    shop_name = str(getattr(product, "shop_name", "") or "以页面为准").strip()
    lines = [
        "先给你放 1 个当前更稳的入口商品：",
        "",
        title,
        f"到手参考：{_stable_price_text(product)}",
        f"店铺：{shop_name}",
        f"理由：{_stable_reason(product)}",
        f"{LABEL_BUY}：{_stable_promotion_redirect_url(product, wechat_openid=wechat_openid, scene='find_product_entry', slot=1)}",
        "",
        "你也可以直接回复想买的商品，比如：卫生纸、洗衣液、宝宝湿巾。",
    ]
    return "\n".join(lines).strip()
# <<< STABLE_CYCLE_OVERRIDE_END <<<


# >>> STABLE_TEMPLATE_V2_BEGIN >>>
import math as _stable_math

def _stable_v2_to_decimal(value):
    try:
        if value is None or value == "":
            return None
        return Decimal(str(value))
    except Exception:
        return None

def _stable_v2_to_int(value, default=0):
    try:
        return int(value or 0)
    except Exception:
        return default

def _stable_v2_to_float(value, default=0.0):
    try:
        return float(value or 0.0)
    except Exception:
        return default

def _stable_v2_h5_url(product, *, scene: str, slot: int) -> str:
    return f"{_base_url()}/api/h5/recommend/{int(getattr(product, 'id'))}?scene={scene}&slot={slot}"

def _stable_v2_redirect_url(product, *, wechat_openid: str, scene: str, slot: int) -> str:
    return (
        f"{_base_url()}/api/promotion/redirect"
        f"?wechat_openid={wechat_openid}"
        f"&product_id={int(getattr(product, 'id'))}"
        f"&scene={scene}"
        f"&slot={slot}"
    )

def _stable_v2_price_text(product) -> str:
    purchase_price = _stable_v2_to_decimal(getattr(product, "purchase_price", None))
    basis_price = _stable_v2_to_decimal(getattr(product, "basis_price", None))
    coupon_price = _stable_v2_to_decimal(getattr(product, "coupon_price", None))
    price = _stable_v2_to_decimal(getattr(product, "price", None))

    if (
        purchase_price is not None
        and basis_price is not None
        and purchase_price > 0
        and basis_price > 0
        and purchase_price < basis_price
    ):
        delta = basis_price - purchase_price
        return f"优惠价￥{purchase_price:.2f}｜京东官网价￥{basis_price:.2f}｜立省￥{delta:.2f}"

    final_price = coupon_price if coupon_price is not None and coupon_price > 0 else price
    if final_price is not None and final_price > 0:
        return f"优惠价￥{final_price:.2f}（以下单页实时为准）"
    return "以下单页实时信息为准，先到先得。"

def _stable_v2_reason(product) -> str:
    sales_volume = _stable_v2_to_int(getattr(product, "sales_volume", None))
    good_comments_share = _stable_v2_to_float(getattr(product, "good_comments_share", None))
    comment_count = _stable_v2_to_int(getattr(product, "comment_count", None))

    purchase_price = _stable_v2_to_decimal(getattr(product, "purchase_price", None))
    basis_price = _stable_v2_to_decimal(getattr(product, "basis_price", None))
    discount_rate = 0.0
    if (
        purchase_price is not None
        and basis_price is not None
        and purchase_price > 0
        and basis_price > 0
        and purchase_price < basis_price
    ):
        discount_rate = float((basis_price - purchase_price) / basis_price)

    if sales_volume >= 300:
        return "近期下单更扎实，属于更容易放心下手的一类。"
    if discount_rate >= 0.30 and comment_count >= 5000:
        return "这单优惠幅度已经拉开，同时评论沉淀更充分，适合先看实时页面。"
    if good_comments_share >= 98 and comment_count >= 5000:
        return "口碑和评论基数都更稳，属于更省心的一档。"
    if sales_volume >= 50 and good_comments_share >= 95:
        return "价格、销量和口碑已经过一轮筛选，适合先看实时页面再决定。"
    return "先把高频对比动作省掉，点开看实时页面即可判断是否值得下单。"

def _stable_v2_score(product) -> float:
    purchase_price = _stable_v2_to_decimal(getattr(product, "purchase_price", None))
    basis_price = _stable_v2_to_decimal(getattr(product, "basis_price", None))
    sales_volume = max(0, _stable_v2_to_int(getattr(product, "sales_volume", None)))
    good_comments_share = max(0.0, min(100.0, _stable_v2_to_float(getattr(product, "good_comments_share", None))))
    comment_count = max(0, _stable_v2_to_int(getattr(product, "comment_count", None)))
    merchant_recommendable = 1.0 if bool(getattr(product, "merchant_recommendable", False)) else 0.0

    discount_rate = 0.0
    if (
        purchase_price is not None
        and basis_price is not None
        and purchase_price > 0
        and basis_price > 0
        and purchase_price < basis_price
    ):
        discount_rate = float((basis_price - purchase_price) / basis_price)

    sales_score = min(1.0, _stable_math.log10(sales_volume + 1) / 3.0)
    comment_score = min(1.0, _stable_math.log10(comment_count + 1) / 5.0)
    good_comment_score = good_comments_share / 100.0
    return round(
        0.34 * discount_rate
        + 0.31 * sales_score
        + 0.20 * comment_score
        + 0.10 * good_comment_score
        + 0.05 * merchant_recommendable,
        6,
    )

def _stable_v2_candidate_pool(db):
    rows = (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.allow_proactive_push.is_(True),
            Product.compliance_level == "normal",
            Product.short_url.isnot(None),
            Product.short_url != "",
        )
        .all()
    )

    rows = sorted(rows, key=_stable_v2_score, reverse=True)

    diversified = []
    used_shop = set()
    used_cat = set()

    for row in rows:
        shop = str(getattr(row, "shop_name", "") or "").strip().lower()
        cat = str(getattr(row, "category_name", "") or "").strip().lower()
        if shop and shop not in used_shop and cat and cat not in used_cat:
            diversified.append(row)
            used_shop.add(shop)
            used_cat.add(cat)

    existing_ids = {int(getattr(x, "id")) for x in diversified if getattr(x, "id", None) is not None}
    for row in rows:
        rid = int(getattr(row, "id"))
        if rid not in existing_ids:
            diversified.append(row)
            existing_ids.add(rid)

    return diversified

def _stable_v2_exposed_ids(db, *, openid_hash: str, scene: str, candidate_ids: list[int]) -> list[int]:
    if not candidate_ids:
        return []
    rows = (
        db.query(WechatRecommendExposure.product_id)
        .filter(
            WechatRecommendExposure.openid_hash == openid_hash,
            WechatRecommendExposure.scene == scene,
            WechatRecommendExposure.product_id.in_(candidate_ids),
        )
        .order_by(WechatRecommendExposure.id.asc())
        .all()
    )
    return [int(x[0]) for x in rows if x and x[0] is not None]

def _stable_v2_pick_batch(db, *, wechat_openid: str, scene: str, batch_size: int):
    pool = list(_stable_v2_candidate_pool(db) or [])
    if not pool:
        return []

    pool_ids = [int(getattr(x, "id")) for x in pool if getattr(x, "id", None) is not None]
    openid_hash = _openid_key(wechat_openid)
    exposed_ids = set(_stable_v2_exposed_ids(db, openid_hash=openid_hash, scene=scene, candidate_ids=pool_ids))

    remaining = [x for x in pool if int(getattr(x, "id")) not in exposed_ids]
    if len(remaining) >= batch_size:
        return remaining[:batch_size]

    if remaining:
        need = batch_size - len(remaining)
        refill = [x for x in pool if int(getattr(x, "id")) not in {int(getattr(y, "id")) for y in remaining}]
        return (remaining + refill[:need])[:batch_size]

    return pool[:batch_size]

def _select_today_batch(db, *, wechat_openid: str):
    batch_size = 3
    try:
        batch_size = int((((_WECHAT_RECOMMEND_RULES or {}).get("today_recommend") or {}).get("batch_size")) or 3)
    except Exception:
        batch_size = 3
    batch_size = max(1, batch_size)
    return _stable_v2_pick_batch(
        db,
        wechat_openid=wechat_openid,
        scene=TODAY_RECOMMEND_SCENE,
        batch_size=batch_size,
    )

def _find_entry_product(db, *, wechat_openid: str):
    picked = _stable_v2_pick_batch(
        db,
        wechat_openid=wechat_openid,
        scene="find_product_entry",
        batch_size=1,
    )
    return picked[0] if picked else None

def get_today_recommend_text_reply(db, wechat_openid: str):
    batch = _select_today_batch(db, wechat_openid=wechat_openid)
    if not batch:
        return "📦 当前推荐池暂无合适商品，稍后再来看看。"

    _record_exposures(
        db,
        openid_hash=_openid_key(wechat_openid),
        scene=TODAY_RECOMMEND_SCENE,
        products=batch,
    )

    lines = [f"🔥 今日推荐 {len(batch)} 个，可直接购买：", ""]
    for idx, product in enumerate(batch, 1):
        lines.extend([
            f"【{idx}】{str(getattr(product, 'title', '') or '').strip()}",
            f"💰 到手参考：{_stable_v2_price_text(product)}",
            f"✨ 推荐理由：{_stable_v2_reason(product)}",
            f"📄 图文详情：{_stable_v2_h5_url(product, scene=TODAY_RECOMMEND_SCENE, slot=idx)}",
            f"🛒 下单链接：{_stable_v2_redirect_url(product, wechat_openid=wechat_openid, scene=TODAY_RECOMMEND_SCENE, slot=idx)}",
            "",
        ])
    lines.append("👉 再点一次“今日推荐”，继续下一组 3 个。")
    return "\n".join(lines).strip()

def get_find_product_entry_text_reply(db, wechat_openid: str):
    product = _find_entry_product(db, wechat_openid=wechat_openid)
    if not product:
        return "📦 当前还没有合适商品，直接回复想买的商品也可以，比如：卫生纸、洗衣液、宝宝湿巾。"

    _record_exposures(
        db,
        openid_hash=_openid_key(wechat_openid),
        scene="find_product_entry",
        products=[product],
    )

    lines = [
        "🔥 先给你放 1 个当前更稳的入口商品：",
        "",
        f"【1】{str(getattr(product, 'title', '') or '').strip()}",
        f"💰 到手参考：{_stable_v2_price_text(product)}",
        f"✨ 推荐理由：{_stable_v2_reason(product)}",
        f"📄 图文详情：{_stable_v2_h5_url(product, scene='find_product_entry', slot=1)}",
        f"🛒 下单链接：{_stable_v2_redirect_url(product, wechat_openid=wechat_openid, scene='find_product_entry', slot=1)}",
        "",
        "👉 也可以直接回复你想买的商品，比如：卫生纸、洗衣液、宝宝湿巾。",
    ]
    return "\n".join(lines).strip()
# <<< STABLE_TEMPLATE_V2_END <<<

# >>> COMMERCIAL_TEMPLATE_OVERRIDE_BEGIN >>>
import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import func

def _cfg():
    try:
        with open("config/wechat_recommend_rules.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _cfg_label(key: str, default: str) -> str:
    return str((_cfg().get("labels") or {}).get(key) or default)

def _cfg_url_template(key: str, default: str) -> str:
    return str((_cfg().get("url") or {}).get(key) or default)

LABEL_BUY = _cfg_label("buy", "下单链接")
LABEL_DETAIL = _cfg_label("detail", "图文详情")
LABEL_MORE = _cfg_label("more_like_this", "更多同类产品")

def _public_base_url() -> str:
    try:
        from app.core.wechat_recommend_config import PUBLIC_BASE_URL
        if PUBLIC_BASE_URL:
            return str(PUBLIC_BASE_URL).rstrip("/")
    except Exception:
        pass
    return "https://aidealfy.kindafeelfy.cn"

def _promotion_url(product, *, wechat_openid: str, scene: str, slot: int) -> str:
    tpl = _cfg_url_template(
        "promotion_redirect_path_template",
        "/api/promotion/redirect?wechat_openid={wechat_openid}&product_id={product_id}&scene={scene}&slot={slot}",
    )
    return _public_base_url() + tpl.format(
        wechat_openid=quote(str(wechat_openid), safe=""),
        product_id=int(product.id),
        scene=quote(str(scene), safe=""),
        slot=int(slot),
    )

def _detail_url(product, *, scene: str, slot: int) -> str:
    tpl = _cfg_url_template(
        "recommend_h5_path_template",
        "/api/h5/recommend/{product_id}?scene={scene}&slot={slot}",
    )
    return _public_base_url() + tpl.format(
        product_id=int(product.id),
        scene=quote(str(scene), safe=""),
        slot=int(slot),
    )

def _more_like_this_url(product, *, scene: str, slot: int, wechat_openid: str = "") -> str:
    tpl = _cfg_url_template(
        "more_like_this_path_template",
        "/api/h5/recommend/more-like-this?product_id={product_id}&scene={scene}&slot={slot}",
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

def _openid_key(openid: str) -> str:
    return hashlib.sha1(str(openid).encode("utf-8")).hexdigest()[:24]

def _product_category_key(product) -> str:
    return str((getattr(product, "category_name", "") or "")).strip().lower()

def _product_shop_key(product) -> str:
    return str((getattr(product, "shop_name", "") or "")).strip().lower()

def _recent_scene_product_ids(db, *, openid_hash: str, scene: str, dedup_days: int = 0) -> set[int]:
    q = db.query(WechatRecommendExposure.product_id).filter(
        WechatRecommendExposure.openid_hash == openid_hash,
        WechatRecommendExposure.scene == scene,
    )
    if dedup_days and dedup_days > 0:
        since_at = datetime.now(timezone.utc) - timedelta(days=dedup_days)
        q = q.filter(WechatRecommendExposure.created_at >= since_at)
    return {int(x[0]) for x in q.all() if x and x[0] is not None}

def _record_scene_exposures(db, *, openid_hash: str, scene: str, products: list):
    rows = []
    for product in products:
        rows.append(
            WechatRecommendExposure(
                openid_hash=openid_hash,
                scene=scene,
                product_id=int(product.id),
            )
        )
    if rows:
        db.add_all(rows)
        db.commit()

def _commercial_reason(product) -> str:
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

def _format_price_line(product) -> str:
    try:
        from app.services.recommend_price_copy_service import format_recommend_price_text
        txt = format_recommend_price_text(product)
        if txt:
            return txt
    except Exception:
        pass
    pp = getattr(product, "purchase_price", None)
    bp = getattr(product, "basis_price", None)
    if pp is not None and bp is not None:
        try:
            return f"优惠价￥{float(pp):.2f}｜京东官网价￥{float(bp):.2f}｜立省￥{float(bp)-float(pp):.2f}"
        except Exception:
            pass
    return "价格以下单页实时信息为准"

def _stable_active_products(db):
    q = (
        db.query(Product)
        .filter(Product.status == "active")
        .filter(Product.allow_proactive_push == True)
        .filter(Product.short_url.isnot(None), Product.short_url != "")
        .filter(Product.purchase_price.isnot(None))
        .filter(Product.basis_price.isnot(None))
        .filter(Product.purchase_price < Product.basis_price)
    )
    rows = list(q.all())
    return rows

def _score(p):
    purchase = float(getattr(p, "purchase_price", 0) or 0)
    basis = float(getattr(p, "basis_price", 0) or 0)
    delta = max(basis - purchase, 0.0)
    discount_rate = (delta / basis) if basis > 0 else 0.0
    sales = float(getattr(p, "sales_volume", 0) or 0)
    comments = float(getattr(p, "comment_count", 0) or 0)
    good = float(getattr(p, "good_comments_share", 0) or 0)

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

def _select_today_batch(db, *, wechat_openid: str):
    scene = "today_recommend"
    openid_hash = _openid_key(wechat_openid)
    products = _stable_active_products(db)
    if not products:
        return []

    products = sorted(products, key=lambda x: (_score(x), int(getattr(x, "comment_count", 0) or 0)), reverse=True)

    exposed_ids = _recent_scene_product_ids(db, openid_hash=openid_hash, scene=scene, dedup_days=0)
    fresh = [p for p in products if int(p.id) not in exposed_ids]
    if len(fresh) < 3:
        exposed_ids = set()
        fresh = list(products)

    batch = []
    used_categories = set()
    used_shops = set()

    for p in fresh:
        cat = _product_category_key(p)
        shop = _product_shop_key(p)
        if cat and cat in used_categories:
            continue
        if shop and shop in used_shops and len(batch) < 2:
            continue
        batch.append(p)
        if cat:
            used_categories.add(cat)
        if shop:
            used_shops.add(shop)
        if len(batch) >= 3:
            break

    if len(batch) < 3:
        used_ids = {int(x.id) for x in batch}
        for p in fresh:
            if int(p.id) in used_ids:
                continue
            batch.append(p)
            used_ids.add(int(p.id))
            if len(batch) >= 3:
                break

    return batch[:3]

def _find_entry_product(db, *, wechat_openid: str):
    batch = _select_today_batch(db, wechat_openid=wechat_openid)
    return batch[0] if batch else None

def has_today_recommend_products(db):
    return len(_stable_active_products(db)) > 0

def has_find_entry_product(db):
    return _find_entry_product(db, wechat_openid="compat_check_openid") is not None

def get_today_recommend_text_reply(db, wechat_openid: str) -> str | None:
    batch = _select_today_batch(db, wechat_openid=wechat_openid)
    if not batch:
        return "当前可推荐商品还在整理中，稍后再试。"

    openid_hash = _openid_key(wechat_openid)
    _record_scene_exposures(db, openid_hash=openid_hash, scene="today_recommend", products=batch)

    lines = ["🔥 今日推荐 3 个，可直接购买：", ""]
    for idx, product in enumerate(batch, 1):
        lines.extend([
            f"【{idx}】{getattr(product, 'title', '')}",
            f"💰 到手参考：{_format_price_line(product)}",
            f"✨ 推荐理由：{_commercial_reason(product)}",
            f"📄 {LABEL_DETAIL}：{_detail_url(product, scene='today_recommend', slot=idx)}",
            f"🛒 {LABEL_BUY}：{_promotion_url(product, wechat_openid=wechat_openid, scene='today_recommend', slot=idx)}",
            f"🔎 {LABEL_MORE}：{_more_like_this_url(product, scene='today_recommend', slot=idx, wechat_openid=wechat_openid)}",
            "",
        ])
    lines.append("👉 再点一次“今日推荐”，继续下一组 3 个。")
    return "\n".join(lines).strip()

def get_find_product_entry_text_reply(db, wechat_openid: str) -> str | None:
    product = _find_entry_product(db, wechat_openid=wechat_openid)
    if not product:
        return "你也可以直接回复想买的商品，比如：卫生纸、洗衣液、宝宝湿巾。"

    openid_hash = _openid_key(wechat_openid)
    _record_scene_exposures(db, openid_hash=openid_hash, scene="find_product_entry", products=[product])

    return "\n".join([
        "🔥 先给你放 1 个当前更稳的入口商品：",
        "",
        f"【1】{getattr(product, 'title', '')}",
        f"💰 到手参考：{_format_price_line(product)}",
        f"✨ 推荐理由：{_commercial_reason(product)}",
        f"📄 {LABEL_DETAIL}：{_detail_url(product, scene='find_product_entry', slot=1)}",
        f"🛒 {LABEL_BUY}：{_promotion_url(product, wechat_openid=wechat_openid, scene='find_product_entry', slot=1)}",
        f"🔎 {LABEL_MORE}：{_more_like_this_url(product, scene='find_product_entry', slot=1, wechat_openid=wechat_openid)}",
        "",
        "👉 也可以直接回复你想买的商品，比如：卫生纸、洗衣液、宝宝湿巾。",
    ]).strip()
# <<< COMMERCIAL_TEMPLATE_OVERRIDE_END <<<

# >>> H5_RENDER_SAFE_OVERRIDE_BEGIN >>>
import html

def render_product_h5(product, *, scene: str = "", slot: str = "") -> str:
    title = html.escape(str(getattr(product, "title", "") or "商品详情"))
    shop_name = html.escape(str(getattr(product, "shop_name", "") or ""))
    category_name = html.escape(str(getattr(product, "category_name", "") or ""))
    image_url = html.escape(str(getattr(product, "image_url", "") or ""))
    detail_url = _detail_url(product, scene=scene or "today_recommend", slot=slot or 1)
    buy_url = _promotion_url(
        product,
        wechat_openid="h5_detail_openid",
        scene=scene or "today_recommend",
        slot=int(slot or 1),
    )
    more_url = _more_like_this_url(product, scene=scene or "today_recommend", slot=int(slot or 1))
    price_text = html.escape(_format_price_line(product))
    reason_text = html.escape(_commercial_reason(product))

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
# <<< H5_RENDER_SAFE_OVERRIDE_END <<<
