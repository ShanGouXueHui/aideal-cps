from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.user import User
from app.services.morning_push_service import generate_morning_push_candidates
from app.services.product_poster_service import (
    build_product_poster_filename,
    generate_product_poster_svg,
)


def _price_text(product: Product) -> str:
    coupon_price = getattr(product, "coupon_price", None)
    price = getattr(product, "price", None)
    value = coupon_price if coupon_price not in (None, 0, "0", "0.0") else price
    return f"¥{float(value or 0):.2f}"


def _reason_text(priority_mode: str, preferred_category: str | None) -> str:
    if priority_mode == "price":
        return f"{preferred_category or '这个品类'}当前优先按更省钱方向筛选，先看这件更划算的。"
    if priority_mode == "quality":
        return f"{preferred_category or '这个品类'}当前优先按质量和口碑稳定性筛选，这件更稳。"
    if priority_mode == "sales":
        return f"{preferred_category or '这个品类'}当前优先按销量和大众接受度筛选，这件更热门。"
    if priority_mode == "self_operated":
        return f"{preferred_category or '这个品类'}当前优先按京东自营 / 更省心方向筛选，这件更合适。"
    return f"{preferred_category or '这个品类'}当前综合价格、口碑和店铺稳定性后，这件更值得先看。"


def build_morning_push_job(
    db: Session,
    *,
    current_hour: int = 8,
    limit: int = 20,
    output_root: str = "data/morning_push_jobs",
    mark_sent: bool = False,
) -> dict:
    candidates = generate_morning_push_candidates(db, current_hour=current_hour, limit=limit)

    now = datetime.now()
    batch_dir = Path(output_root) / now.strftime("%Y%m%d") / now.strftime("%H%M%S")
    posters_dir = batch_dir / "posters"
    batch_dir.mkdir(parents=True, exist_ok=True)
    posters_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []

    for item in candidates:
        user = db.query(User).filter(User.id == item["user_id"]).first()
        product = db.query(Product).filter(Product.id == item["product_id"]).first()
        if not user or not product:
            continue

        poster_filename = build_product_poster_filename(product.id, product.title)
        poster_path = posters_dir / poster_filename
        reason_text = _reason_text(item["priority_mode"], item["preferred_category"])

        generate_product_poster_svg(
            title=product.title,
            shop_name=product.shop_name,
            category_name=product.category_name,
            price_text=_price_text(product),
            reason_text=reason_text,
            link_text=f"/api/promotion/redirect?wechat_openid={user.wechat_openid}&product_id={product.id}&scene=morning_push&slot=1",
            badge_text="今日值得看",
            output_path=str(poster_path),
        )

        row = {
            "user_id": user.id,
            "wechat_openid": user.wechat_openid,
            "product_id": product.id,
            "priority_mode": item["priority_mode"],
            "preferred_category": item["preferred_category"],
            "message": item["message"],
            "poster_reason": reason_text,
            "poster_path": str(poster_path),
        }
        rows.append(row)

        if mark_sent:
            user.last_push_at = now

    if mark_sent:
        db.commit()

    job_payload = {
        "generated_at": now.isoformat(),
        "current_hour": current_hour,
        "count": len(rows),
        "rows": rows,
    }

    job_file = batch_dir / "job.json"
    job_file.write_text(json.dumps(job_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "job_file": str(job_file),
        "count": len(rows),
        "rows": rows,
    }
