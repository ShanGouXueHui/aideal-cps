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

DEFAULT_RULE_PATH = ROOT / "config" / "commission_candidate_pool_rules.json"

ROOT.joinpath("run").mkdir(exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    return any(k and k.lower() in t for k in keywords)


def hit_terms(text: str | None, keywords: list[str]) -> list[str]:
    t = str(text or "").lower()
    return [k for k in keywords if k and k.lower() in t]


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


def saving(p: Product) -> tuple[Decimal, Decimal]:
    ep = effective_price(p)
    bp = basis_price(p)
    if ep is None or bp is None or bp <= 0:
        return Decimal("0"), Decimal("0")
    saved = bp - ep
    rate = saved / bp if bp > 0 else Decimal("0")
    return saved, rate


def identity(title: str | None) -> str:
    t = str(title or "").lower()
    t = re.sub(r"[\s\W_]+", "", t)
    t = re.sub(r"\d+(\.\d+)?(g|kg|ml|l|片|包|支|瓶|袋|只|个|件|卷|抽|颗|粒|盒|箱|支装|瓶装|包装)", "", t)
    return t[:56]


def classify_product(p: Product, rules: dict[str, Any]) -> tuple[str, list[str]]:
    hard = rules.get("hard_block") or {}
    managed = rules.get("managed_category") or {}
    safe_core_terms = [str(x) for x in rules.get("safe_core_category_keywords") or []]
    policy = rules.get("tier_policy") or {}

    title = p.title or ""
    category = p.category_name or ""
    shop = p.shop_name or ""

    hard_hits = []
    hard_hits += [f"title:{x}" for x in hit_terms(title, [str(v) for v in hard.get("title_keywords") or []])]
    hard_hits += [f"category:{x}" for x in hit_terms(category, [str(v) for v in hard.get("category_keywords") or []])]
    hard_hits += [f"shop:{x}" for x in hit_terms(shop, [str(v) for v in hard.get("shop_keywords") or []])]
    if hard_hits:
        return "blocked", hard_hits

    ep = effective_price(p)
    if ep is None or ep < Decimal(str(policy.get("min_effective_price", 3))):
        return "blocked", ["price:low_or_missing"]
    if ep > Decimal(str(policy.get("max_effective_price_broad", 2000))):
        return "blocked", ["price:too_high"]

    commission = D(p.estimated_commission) or Decimal("0")
    if commission < Decimal(str(policy.get("min_estimated_commission", 0.03))):
        return "blocked", ["commission:too_low"]

    managed_hits = []
    managed_hits += [f"title:{x}" for x in hit_terms(title, [str(v) for v in managed.get("title_keywords") or []])]
    managed_hits += [f"category:{x}" for x in hit_terms(category, [str(v) for v in managed.get("category_keywords") or []])]
    if managed_hits:
        return "managed_review", managed_hits

    has_short = bool((p.short_url or "").strip())
    sales = int(p.sales_volume or 0)
    saved, saved_rate = saving(p)
    positive_saving = (
        saved >= Decimal(str(policy.get("min_saved_amount", 2)))
        and saved_rate >= Decimal(str(policy.get("min_saved_rate", 0.03)))
    )
    safe_core = contains_any(category, safe_core_terms)

    if (
        safe_core
        and has_short
        and ep <= Decimal(str(policy.get("max_effective_price_main_ready", 399)))
        and commission >= Decimal(str(policy.get("main_ready_min_estimated_commission", 0.08)))
        and sales >= int(policy.get("main_ready_min_sales_volume", 50))
        and (positive_saving or not bool(policy.get("main_ready_require_positive_saving", True)))
    ):
        return "main_ready", []

    if safe_core:
        return ("semi_ready_missing_short_url" if not has_short else "semi_ready"), []

    return "broad_candidate", []


def score_product(p: Product, tier: str, rules: dict[str, Any]) -> float:
    weights = rules.get("score_weights") or {}
    saved, saved_rate = saving(p)

    sales = int(p.sales_volume or 0)
    commission = float(D(p.estimated_commission) or Decimal("0"))
    has_short = bool((p.short_url or "").strip())
    exact = bool(p.is_exact_discount and p.price_verified_at)

    score = 0.0
    score += math.log10(max(sales, 0) + 1) * float(weights.get("sales_weight", 10))
    score += min(commission, 80.0) * float(weights.get("commission_weight", 1.2))
    score += min(float(max(saved, Decimal("0"))), 150.0) * float(weights.get("saved_amount_weight", 0.25))
    score += min(float(max(saved_rate, Decimal("0"))), 0.8) * float(weights.get("saved_rate_weight", 30))
    if has_short:
        score += float(weights.get("short_url_bonus", 10))
    else:
        score += float(weights.get("missing_short_url_penalty", -6))
    if exact:
        score += float(weights.get("exact_price_bonus", 8))
    if tier.startswith("main") or tier.startswith("semi"):
        score += float(weights.get("safe_core_bonus", 12))
    if tier == "managed_review":
        score += float(weights.get("managed_penalty", -25))
    return round(score, 4)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules-path", default=str(DEFAULT_RULE_PATH))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    rules = load_json(Path(args.rules_path))
    output = rules.get("output") or {}
    candidate_path = ROOT / str(output.get("candidate_path", "run/commission_candidate_pool.json"))
    status_path = ROOT / str(output.get("status_path", "run/commission_candidate_pool_status.json"))
    max_output = int(output.get("max_output", 100000))
    if args.limit and args.limit > 0:
        max_output = min(max_output, args.limit)

    db = SessionLocal()
    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    reject_reasons: Counter[str] = Counter()
    seen_identity: set[str] = set()

    try:
        q = db.query(Product).filter(Product.status == "active").order_by(Product.id.asc())
        for p in q.yield_per(1000):
            counters["active_scanned"] += 1

            material = (p.material_url or p.product_url or "").strip()
            if not material:
                reject_reasons["missing_material"] += 1
                continue

            tier, reasons = classify_product(p, rules)
            if tier == "blocked":
                counters["blocked"] += 1
                for r in reasons:
                    reject_reasons[r] += 1
                continue

            ident = identity(p.title)
            if ident and ident in seen_identity:
                counters["near_duplicate_skipped"] += 1
                continue
            seen_identity.add(ident)

            ep = effective_price(p)
            bp = basis_price(p)
            saved, saved_rate = saving(p)
            score = score_product(p, tier, rules)
            categories[p.category_name or "未知类目"] += 1
            counters[tier] += 1

            rows.append({
                "id": p.id,
                "jd_sku_id": p.jd_sku_id,
                "tier": tier,
                "score": score,
                "title": (p.title or "")[:180],
                "category_name": p.category_name,
                "shop_name": p.shop_name,
                "effective_price": str(ep) if ep is not None else None,
                "basis_price": str(bp) if bp is not None else None,
                "saved_amount": str(saved),
                "saved_rate": str(round(float(saved_rate), 4)),
                "estimated_commission": str(D(p.estimated_commission) or Decimal("0")),
                "sales_volume": int(p.sales_volume or 0),
                "has_short_url": bool((p.short_url or "").strip()),
                "short_url": p.short_url if (p.short_url or "").strip() else None,
                "has_price_verified_at": bool(p.price_verified_at),
                "is_exact_discount": bool(p.is_exact_discount),
                "risk_reasons": reasons,
                "identity": ident
            })

        rows.sort(key=lambda x: (
            {"main_ready": 5, "semi_ready": 4, "semi_ready_missing_short_url": 3, "broad_candidate": 2, "managed_review": 1}.get(x["tier"], 0),
            float(x["score"])
        ), reverse=True)
        rows = rows[:max_output]

        tier_counts = Counter([x["tier"] for x in rows])
        status = {
            "job": "build_commission_candidate_pool",
            "status": "success",
            "updated_at": now_iso(),
            "rules_path": str(args.rules_path),
            "active_scanned": counters["active_scanned"],
            "candidate_count": len(rows),
            "tier_counts": dict(tier_counts),
            "source_counters": dict(counters),
            "top_categories": categories.most_common(80),
            "reject_reasons": reject_reasons.most_common(80)
        }

        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_text(json.dumps({
            "job": "commission_candidate_pool",
            "updated_at": now_iso(),
            "candidate_count": len(rows),
            "candidates": rows
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

        print(json.dumps(status, ensure_ascii=False), flush=True)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
