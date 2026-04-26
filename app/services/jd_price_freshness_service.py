from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.product import Product

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "jd_price_refresh_policy.json"


def _load_policy() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("load jd price refresh policy failed")
        return {}


def _now() -> datetime:
    return datetime.utcnow()


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return None


def _mark_checked(product: Product) -> None:
    if hasattr(product, "price_verified_at"):
        setattr(product, "price_verified_at", _now())


def _has_strict_verified_price(product: Product) -> bool:
    try:
        purchase = float(getattr(product, "purchase_price", 0) or 0)
        basis = float(getattr(product, "basis_price", 0) or 0)
    except Exception:
        return False
    return bool(getattr(product, "is_exact_discount", False)) and purchase > 0 and basis > purchase


def should_refresh_product_price(product: Product, *, trigger: str = "h5_detail", force: bool = False) -> bool:
    if force:
        return True

    policy = _load_policy()
    if not bool(policy.get("enabled", True)):
        return False

    if not getattr(product, "jd_sku_id", None):
        return False

    interval_key = "h5_detail_refresh_interval_hours" if trigger == "h5_detail" else "background_refresh_interval_hours"
    interval_hours = _to_int(policy.get(interval_key), 72)
    if interval_hours <= 0:
        interval_hours = 72

    last_checked = _to_dt(getattr(product, "price_verified_at", None))
    if last_checked is None:
        return True

    return (_now() - last_checked) >= timedelta(hours=interval_hours)


def refresh_product_price_if_stale(
    db: Session,
    product: Product,
    *,
    trigger: str = "h5_detail",
    force: bool = False,
) -> Product:
    """Refresh JD price only when stale, and throttle repeated calls.

    This function intentionally records a check timestamp even when JD does not
    return a strict price snapshot, so one product will not repeatedly hit JD
    on every H5 page view.
    """
    if product is None:
        return product

    if not should_refresh_product_price(product, trigger=trigger, force=force):
        return product

    policy = _load_policy()
    before_checked = getattr(product, "price_verified_at", None)

    try:
        from app.services.jd_exact_price_service import refresh_single_product_exact_price

        refreshed = refresh_single_product_exact_price(db, product) or product

        after_checked = getattr(refreshed, "price_verified_at", None)
        if after_checked == before_checked or after_checked is None:
            _mark_checked(refreshed)

        if hasattr(refreshed, "is_exact_discount") and not _has_strict_verified_price(refreshed):
            setattr(refreshed, "is_exact_discount", False)

        db.flush()
        return refreshed
    except Exception:
        logger.exception(
            "jd price refresh failed | product_id=%s trigger=%s",
            getattr(product, "id", None),
            trigger,
        )
        if bool(policy.get("throttle_on_failure", True)):
            _mark_checked(product)
            if hasattr(product, "is_exact_discount"):
                setattr(product, "is_exact_discount", False)
            db.flush()
        return product


def _extract_product_ids_from_obj(obj: Any, out: set[int]) -> None:
    if isinstance(obj, dict):
        for key in ("id", "product_id", "productId"):
            value = obj.get(key)
            try:
                if value is not None and int(value) > 0:
                    out.add(int(value))
            except Exception:
                pass
        for value in obj.values():
            _extract_product_ids_from_obj(value, out)
    elif isinstance(obj, list):
        for value in obj:
            _extract_product_ids_from_obj(value, out)


def _load_recommendation_whitelist_product_ids() -> list[int]:
    root = Path(__file__).resolve().parents[2]
    candidates = [
        root / "run" / "proactive_recommend_whitelist.json",
        root / "run" / "wechat_recommend_whitelist.json",
        root / "data" / "proactive_recommend_whitelist.json",
    ]
    out: set[int] = set()
    for path in candidates:
        if not path.exists():
            continue
        try:
            _extract_product_ids_from_obj(json.loads(path.read_text(encoding="utf-8")), out)
        except Exception:
            logger.exception("load recommendation whitelist failed | path=%s", path)
    return sorted(out)


def refresh_stale_recommendation_pool_prices(db: Session, *, limit: int | None = None) -> dict[str, Any]:
    """Refresh JD exact prices for current high-quality recommendation pool.

    Priority:
    1. product ids from generated recommendation whitelist;
    2. fallback to active products ordered by stale price_verified_at.
    """
    policy = _load_policy()
    max_limit = int(limit or policy.get("background_limit_per_run") or 50)
    product_ids = _load_recommendation_whitelist_product_ids()

    query = db.query(Product).filter(Product.status == "active")

    if product_ids:
        query = query.filter(Product.id.in_(product_ids))
    else:
        query = query.filter(Product.jd_sku_id.isnot(None), Product.jd_sku_id != "")

    rows = query.order_by(Product.price_verified_at.isnot(None), Product.price_verified_at.asc(), Product.id.asc()).limit(max_limit).all()

    refreshed = 0
    skipped = 0
    failed = 0

    for product in rows:
        try:
            if should_refresh_product_price(product, trigger="background"):
                refresh_product_price_if_stale(db, product, trigger="background")
                refreshed += 1
            else:
                skipped += 1
        except Exception:
            failed += 1
            logger.exception("refresh recommendation pool price failed | product_id=%s", getattr(product, "id", None))

    db.flush()
    return {
        "candidate_count": len(rows),
        "refreshed": refreshed,
        "skipped": skipped,
        "failed": failed,
        "source": "whitelist" if product_ids else "active_products",
        "limit": max_limit,
    }
