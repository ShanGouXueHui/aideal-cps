from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Query, Session

from app.models.product import Product
from app.services.product_compliance_config_service import load_product_compliance_rules


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: str, keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for keyword in keywords:
        if keyword and keyword.lower() in text:
            hits.append(keyword)
    return hits


def classify_product_compliance(
    *,
    title: str | None,
    category_name: str | None,
    shop_name: str | None = None,
    forbid_types: list[int] | None = None,
) -> dict[str, Any]:
    rules = load_product_compliance_rules()

    title_text = _normalize_text(title)
    category_text = _normalize_text(category_name)
    shop_text = _normalize_text(shop_name)
    combined_text = " | ".join([title_text, category_text, shop_text])

    hard_title_hits = _contains_any(combined_text, rules["hard_block_keywords"]["title"])
    hard_category_hits = _contains_any(combined_text, rules["hard_block_keywords"]["category"])
    restricted_title_hits = _contains_any(combined_text, rules["restricted_keywords"]["title"])
    restricted_category_hits = _contains_any(combined_text, rules["restricted_keywords"]["category"])

    forbid_types = forbid_types or []
    forbid_types = [int(x) for x in forbid_types if str(x).strip().isdigit()]
    restricted_forbid = set(int(x) for x in rules["jd_forbid_types_restricted"])

    compliance_level = rules["default_compliance_level"]
    age_gate_required = False
    allow_proactive_push = True
    allow_partner_share = True
    notes: list[str] = []

    if hard_title_hits or hard_category_hits:
        compliance_level = "hard_block"
        allow_proactive_push = False
        allow_partner_share = False
        notes.extend([f"hard_keyword:{x}" for x in hard_title_hits + hard_category_hits])

    elif restricted_title_hits or restricted_category_hits:
        compliance_level = "restricted"
        age_gate_required = True
        allow_proactive_push = False
        allow_partner_share = False
        notes.extend([f"restricted_keyword:{x}" for x in restricted_title_hits + restricted_category_hits])

    elif any(x in restricted_forbid for x in forbid_types):
        compliance_level = "restricted"
        age_gate_required = True
        allow_proactive_push = False
        allow_partner_share = False
        notes.append(f"jd_forbid_types:{','.join(str(x) for x in forbid_types)}")

    if compliance_level not in rules["proactive_push_allowed_levels"]:
        allow_proactive_push = False
    if compliance_level not in rules["partner_share_allowed_levels"]:
        allow_partner_share = False

    return {
        "compliance_level": compliance_level,
        "age_gate_required": age_gate_required,
        "allow_proactive_push": allow_proactive_push,
        "allow_partner_share": allow_partner_share,
        "compliance_notes": " | ".join(notes) if notes else None,
    }


def enrich_product_payload_with_compliance(
    payload: dict[str, Any],
    *,
    forbid_types: list[int] | None = None,
) -> dict[str, Any]:
    meta = classify_product_compliance(
        title=payload.get("title"),
        category_name=payload.get("category_name"),
        shop_name=payload.get("shop_name"),
        forbid_types=forbid_types,
    )
    merged = dict(payload)
    merged.update(meta)
    return merged


def evaluate_product_instance(product: Product) -> dict[str, Any]:
    return classify_product_compliance(
        title=getattr(product, "title", None),
        category_name=getattr(product, "category_name", None),
        shop_name=getattr(product, "shop_name", None),
        forbid_types=None,
    )


def apply_product_visibility_filter(
    query: Query,
    *,
    adult_verified: bool = False,
    require_proactive_push: bool = False,
    require_partner_share: bool = False,
) -> Query:
    rules = load_product_compliance_rules()

    query = query.filter(Product.compliance_level != "hard_block")

    if require_proactive_push:
        return query.filter(
            Product.allow_proactive_push.is_(True),
            Product.compliance_level.in_(rules["proactive_push_allowed_levels"]),
        )

    if require_partner_share:
        return query.filter(
            Product.allow_partner_share.is_(True),
            Product.compliance_level.in_(rules["partner_share_allowed_levels"]),
        )

    visible_levels = rules["adult_visible_levels"] if adult_verified else rules["minor_visible_levels"]
    return query.filter(Product.compliance_level.in_(visible_levels))


def assert_product_partner_share_allowed(product: Product) -> None:
    if getattr(product, "status", None) != "active":
        raise ValueError("Product is not active")
    if getattr(product, "allow_partner_share", False) is not True:
        raise ValueError("Product is not allowed for partner sharing")
    if getattr(product, "compliance_level", "normal") != "normal":
        raise ValueError("Product compliance level does not allow partner sharing")


def backfill_product_compliance(db: Session) -> dict[str, Any]:
    rows = db.query(Product).all()
    updated = 0
    level_counts = {"normal": 0, "restricted": 0, "hard_block": 0}

    for product in rows:
        meta = evaluate_product_instance(product)
        changed = False
        for key, value in meta.items():
            if getattr(product, key, None) != value:
                setattr(product, key, value)
                changed = True
        if changed:
            updated += 1
        level = meta["compliance_level"]
        level_counts[level] = level_counts.get(level, 0) + 1

    db.commit()
    return {
        "total": len(rows),
        "updated": updated,
        "level_counts": level_counts,
    }
