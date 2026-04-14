from __future__ import annotations


def is_normal_compliance(product) -> bool:
    return getattr(product, "compliance_level", None) == "normal"


def is_merchant_recommendable(product) -> bool:
    return bool(getattr(product, "merchant_recommendable", False))


def allow_proactive_recommend(product) -> bool:
    return (
        getattr(product, "status", None) == "active"
        and is_normal_compliance(product)
        and bool(getattr(product, "allow_proactive_push", False))
        and is_merchant_recommendable(product)
    )


def allow_partner_share(product) -> bool:
    return (
        getattr(product, "status", None) == "active"
        and is_normal_compliance(product)
        and bool(getattr(product, "allow_partner_share", False))
        and is_merchant_recommendable(product)
    )


def allow_user_search_display(product) -> bool:
    return (
        getattr(product, "status", None) == "active"
        and getattr(product, "compliance_level", None) != "hard_block"
    )
