from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import SessionLocal
from app.models.product import Product

DEFAULT_RULE_PATH = ROOT / "config" / "proactive_recommend_rules.json"
DEFAULT_OUTPUT_PATH = ROOT / "run" / "semi_recommend_pool_candidates.json"
DEFAULT_STATUS_PATH = ROOT / "run" / "semi_recommend_pool_status.json"
DEFAULT_SEMI_RULE_PATH = ROOT / "config" / "semi_recommend_pool_rules.json"

ROOT.joinpath("run").mkdir(exist_ok=True)
ROOT.joinpath("logs").mkdir(exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_rules(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def D(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        return Decimal(text)
    except Exception:
        return None


def contains_any(text: str | None, keywords: list[str]) -> bool:
    t = str(text or "").lower()
    return any(k and k in t for k in keywords)


def normalize_identity(title: str | None) -> str:
    t = str(title or "").lower()
    t = re.sub(r"[\s\W_]+", "", t)
    t = re.sub(r"\d+(\.\d+)?(g|kg|ml|l|片|包|支|瓶|袋|只|个|件|卷|抽|颗|粒|盒|箱|支装|瓶装|包装)", "", t)
    t = re.sub(r"(升级款|新款|旗舰款|促销装|家庭装|实惠装|组合装|套装)", "", t)
    return t[:48]


def effective_price(p: Product) -> Decimal | None:
    for value in (p.purchase_price, p.coupon_price, p.price):
        v = D(value)
        if v is not None and v > 0:
            return v
    return None


def basis_price(p: Product) -> Decimal | None:
    for value in (p.basis_price, p.price):
        v = D(value)
        if v is not None and v > 0:
            return v
    return None


def saving_snapshot(p: Product, *, min_saved_amount: Decimal, min_saved_rate: Decimal) -> tuple[bool, Decimal, Decimal]:
    ep = effective_price(p)
    bp = basis_price(p)
    if ep is None or bp is None or bp <= 0:
        return False, Decimal("0"), Decimal("0")
    saved = bp - ep
    rate = saved / bp if bp > 0 else Decimal("0")
    ok = saved >= min_saved_amount and rate >= min_saved_rate
    return ok, saved, rate


def score_product(p: Product, saved: Decimal, saved_rate: Decimal, semi_rules: dict[str, Any] | None = None) -> float:
    sales = int(p.sales_volume or 0)
    commission = float(D(p.estimated_commission) or Decimal("0"))
    comment_count = int(p.comment_count or 0)
    good_share = float(p.good_comments_share or 0)
    exact_bonus = 8.0 if bool(p.is_exact_discount and p.price_verified_at) else 0.0
    short_bonus = 6.0 if bool((p.short_url or "").strip()) else 0.0

    sales_score = math.log10(max(sales, 0) + 1) * 12.0
    commission_score = min(commission, 50.0) * 1.8
    saved_score = min(float(saved), 120.0) * 0.35
    saved_rate_score = min(float(saved_rate), 0.8) * 45.0
    comment_score = math.log10(max(comment_count, 0) + 1) * 3.0
    good_share_score = max(0.0, good_share - 0.85) * 30.0 if good_share else 0.0

    semi_rules = semi_rules or {}
    commission_score = min(commission, 50.0) * float(semi_rules.get("commission_weight", 0.9))
    sales_score = math.log10(max(sales, 0) + 1) * float(semi_rules.get("sales_weight", 14.0))
    saved_score = min(float(saved), 120.0) * float(semi_rules.get("saved_amount_weight", 0.35))
    saved_rate_score = min(float(saved_rate), 0.8) * float(semi_rules.get("saved_rate_weight", 45.0))
    exact_bonus = float(semi_rules.get("exact_price_bonus", 8.0)) if bool(p.is_exact_discount and p.price_verified_at) else 0.0
    short_bonus = float(semi_rules.get("short_url_bonus", 6.0)) if bool((p.short_url or "").strip()) else 0.0

    return round(
        sales_score
        + commission_score
        + saved_score
        + saved_rate_score
        + comment_score
        + good_share_score
        + exact_bonus
        + short_bonus,
        4,
    )


def build_candidates(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rules = load_rules(Path(args.rules_path))
    semi_rules = load_rules(Path(args.semi_rules_path)) if Path(args.semi_rules_path).exists() else {}

    exclude_title_keywords = [str(x).lower() for x in rules.get("exclude_title_keywords", [])]
    exclude_category_keywords = [str(x).lower() for x in rules.get("exclude_category_keywords", [])]
    exclude_shop_keywords = [str(x).lower() for x in rules.get("exclude_shop_keywords", [])]

    allowed_semi_categories = [str(x).lower() for x in semi_rules.get("allowed_category_keywords", [])]
    blocked_semi_categories = [str(x).lower() for x in semi_rules.get("blocked_category_keywords", [])]
    blocked_semi_titles = [str(x).lower() for x in semi_rules.get("blocked_title_keywords", [])]

    min_effective_price = Decimal(str(rules.get("min_effective_price", 6)))
    max_effective_price = Decimal(str(semi_rules.get("max_effective_price_stage1", rules.get("max_effective_price", 2000))))
    min_estimated_commission = Decimal(str(rules.get("min_estimated_commission", 0.08)))
    min_sales_volume = int(rules.get("min_sales_volume", 50))
    min_saved_amount = Decimal(str(rules.get("min_saved_amount", 2)))
    min_saved_rate = Decimal(str(rules.get("min_saved_rate", 0.03)))

    db = SessionLocal()
    counters: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    reject_counter: Counter[str] = Counter()
    identity_seen: set[str] = set()
    category_selected: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []

    try:
        query = (
            db.query(Product)
            .filter(Product.status == "active")
            .order_by(Product.id.asc())
        )

        for p in query.yield_per(1000):
            counters["active_scanned"] += 1

            title = p.title or ""
            category = p.category_name or "未知类目"
            shop = p.shop_name or ""
            category_counter[category] += 1

            material = (p.material_url or p.product_url or "").strip()
            if not material:
                reject_counter["missing_material_url"] += 1
                continue

            ep = effective_price(p)
            bp = basis_price(p)
            commission = D(p.estimated_commission) or Decimal("0")
            sales = int(p.sales_volume or 0)

            if contains_any(title, exclude_title_keywords) or contains_any(title, blocked_semi_titles):
                reject_counter["bad_title"] += 1
                continue
            if contains_any(category, exclude_category_keywords) or contains_any(category, blocked_semi_categories):
                reject_counter["bad_category"] += 1
                continue
            if allowed_semi_categories and not contains_any(category, allowed_semi_categories):
                reject_counter["not_in_stage1_allowed_category"] += 1
                continue
            if contains_any(shop, exclude_shop_keywords):
                reject_counter["bad_shop"] += 1
                continue
            if ep is None or ep < min_effective_price:
                reject_counter["low_or_missing_price"] += 1
                continue
            if ep > max_effective_price:
                reject_counter["high_price"] += 1
                continue
            if commission < min_estimated_commission:
                reject_counter["low_commission"] += 1
                continue
            if sales < min_sales_volume:
                reject_counter["low_sales"] += 1
                continue

            saving_ok, saved, saved_rate = saving_snapshot(
                p,
                min_saved_amount=min_saved_amount,
                min_saved_rate=min_saved_rate,
            )
            if not saving_ok:
                reject_counter["no_positive_saving"] += 1
                continue

            identity = normalize_identity(title)
            if identity and identity in identity_seen:
                reject_counter["near_duplicate"] += 1
                continue

            if args.max_per_category > 0 and category_selected[category] >= args.max_per_category:
                reject_counter["category_cap"] += 1
                continue

            score = score_product(p, saved, saved_rate, semi_rules=semi_rules)
            has_short = bool((p.short_url or "").strip())

            item = {
                "id": p.id,
                "jd_sku_id": p.jd_sku_id,
                "title": title[:180],
                "category_name": category,
                "shop_name": shop[:120],
                "score": score,
                "effective_price": str(ep),
                "basis_price": str(bp) if bp is not None else None,
                "saved_amount": str(saved),
                "saved_rate": str(round(float(saved_rate), 4)),
                "estimated_commission": str(commission),
                "sales_volume": sales,
                "comment_count": int(p.comment_count or 0),
                "good_comments_share": p.good_comments_share,
                "has_short_url": has_short,
                "short_url": p.short_url if has_short else None,
                "material_url": material,
                "is_exact_discount": bool(p.is_exact_discount),
                "price_verified_at": p.price_verified_at.isoformat() if p.price_verified_at else None,
                "identity": identity,
            }
            candidates.append(item)
            identity_seen.add(identity)
            category_selected[category] += 1
            counters["candidate_before_limit"] += 1

            if args.scan_limit > 0 and counters["active_scanned"] >= args.scan_limit:
                break

        candidates.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
        if args.candidate_limit > 0:
            candidates = candidates[: args.candidate_limit]

        selected_categories = Counter([x["category_name"] for x in candidates])
        missing_short = sum(1 for x in candidates if not x.get("has_short_url"))
        with_short = len(candidates) - missing_short

        status = {
            "job": "build_semi_recommend_pool",
            "status": "success",
            "updated_at": now_iso(),
            "rules_path": str(args.rules_path),
            "semi_rules_path": str(args.semi_rules_path),
            "semi_stage": semi_rules.get("stage"),
            "active_scanned": counters["active_scanned"],
            "candidate_count": len(candidates),
            "candidate_with_short_url": with_short,
            "candidate_missing_short_url": missing_short,
            "max_per_category": args.max_per_category,
            "top_categories": selected_categories.most_common(50),
            "source_top_categories": category_counter.most_common(50),
            "reject_counts": dict(reject_counter),
        }
        return candidates, status
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules-path", default=str(DEFAULT_RULE_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--status-path", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--semi-rules-path", default=str(DEFAULT_SEMI_RULE_PATH))
    parser.add_argument("--candidate-limit", type=int, default=5000)
    parser.add_argument("--scan-limit", type=int, default=0)
    parser.add_argument("--max-per-category", type=int, default=160)
    args = parser.parse_args()

    candidates, status = build_candidates(args)

    output_path = Path(args.output_path)
    status_path = Path(args.status_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)

    output_payload = {
        "job": "semi_recommend_pool_candidates",
        "updated_at": now_iso(),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    output_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(status, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
