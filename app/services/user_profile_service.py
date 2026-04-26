from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.user import User
from app.services.product_intent_service import parse_product_intent
from app.services.user_crypto_service import decrypt_text, encrypt_text
from app.services.user_profile_config_service import load_user_profile_rules
from app.services.user_service import get_or_create_user_by_openid_db


def _load_category_map(user: User) -> dict[str, int]:
    raw = ""
    if getattr(user, "preferred_categories_ciphertext", None):
        raw = decrypt_text(user.preferred_categories_ciphertext) or ""
    if not raw:
        raw = user.preferred_categories or ""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): int(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def _dump_category_map(data: dict[str, int]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _save_category_map(user: User, data: dict[str, int]) -> None:
    raw = _dump_category_map(data)
    user.preferred_categories = None
    user.preferred_categories_ciphertext = encrypt_text(raw)


def _increase_capped(current: float | None, delta: float, cap: float) -> float:
    value = float(current or 0.0) + float(delta)
    return min(value, float(cap))


def record_subscribe_event(db: Session, openid: str, nickname: str | None = None) -> User:
    user = get_or_create_user_by_openid_db(db, openid, nickname=nickname)
    if not user.first_subscribe_at:
        user.first_subscribe_at = datetime.now(timezone.utc)
    if user.morning_push_enabled is None:
        user.morning_push_enabled = True
    if not user.morning_push_hour:
        user.morning_push_hour = 8
    db.commit()
    db.refresh(user)
    return user


def update_user_profile_from_text(db: Session, openid: str, text: str, nickname: str | None = None) -> User:
    rules = load_user_profile_rules()
    weights = rules["text_weights"]
    caps = rules["score_caps"]

    user = get_or_create_user_by_openid_db(db, openid, nickname=nickname)
    intent = parse_product_intent(text)

    user.last_interaction_at = datetime.now(timezone.utc)
    user.interaction_count = int(user.interaction_count or 0) + 1
    user.last_query_text = None
    user.last_query_text_ciphertext = encrypt_text(text.strip())

    if intent["shopping_intent"]:
        categories = _load_category_map(user)

        if intent.get("commodity"):
            commodity = intent["commodity"]
            categories[commodity] = int(categories.get(commodity, 0)) + int(weights["commodity"])
            _save_category_map(user, categories)

        if intent.get("wants_low_price"):
            user.price_sensitive_score = _increase_capped(
                user.price_sensitive_score,
                weights["wants_low_price"],
                caps["price_sensitive_score"],
            )
        if intent.get("wants_quality"):
            user.quality_sensitive_score = _increase_capped(
                user.quality_sensitive_score,
                weights["wants_quality"],
                caps["quality_sensitive_score"],
            )
        if intent.get("wants_sales"):
            user.sales_sensitive_score = _increase_capped(
                user.sales_sensitive_score,
                weights["wants_sales"],
                caps["sales_sensitive_score"],
            )
        if intent.get("wants_self_operated"):
            user.self_operated_sensitive_score = _increase_capped(
                user.self_operated_sensitive_score,
                weights["wants_self_operated"],
                caps["self_operated_sensitive_score"],
            )

    db.commit()
    db.refresh(user)
    return user


def update_user_profile_from_click(db: Session, user: User, product: Product) -> User:
    rules = load_user_profile_rules()
    weights = rules["click_weights"]
    caps = rules["score_caps"]

    user.last_interaction_at = datetime.now(timezone.utc)

    categories = _load_category_map(user)
    category_name = getattr(product, "category_name", None)
    if category_name:
        categories[category_name] = int(categories.get(category_name, 0)) + int(weights["category"])
        _save_category_map(user, categories)

    price = float(getattr(product, "price", 0) or 0)
    coupon_price = float(getattr(product, "coupon_price", 0) or 0)
    if coupon_price > 0 and price > coupon_price:
        user.price_sensitive_score = _increase_capped(
            user.price_sensitive_score,
            weights["price_sensitive"],
            caps["price_sensitive_score"],
        )

    merchant_health = float(getattr(product, "merchant_health_score", 0) or 0)
    if merchant_health >= 75:
        user.quality_sensitive_score = _increase_capped(
            user.quality_sensitive_score,
            weights["quality_sensitive"],
            caps["quality_sensitive_score"],
        )

    if str(getattr(product, "owner", "") or "") == "g":
        user.self_operated_sensitive_score = _increase_capped(
            user.self_operated_sensitive_score,
            weights["self_operated_sensitive"],
            caps["self_operated_sensitive_score"],
        )

    db.flush()
    return user


def preferred_category(user: User) -> str | None:
    categories = _load_category_map(user)
    if not categories:
        return None
    return sorted(categories.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
