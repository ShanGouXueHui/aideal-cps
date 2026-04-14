from types import SimpleNamespace

from app.services.recommendation_guard_service import (
    allow_partner_share,
    allow_proactive_recommend,
    allow_user_search_display,
)


def test_proactive_recommend_requires_normal_and_merchant_ok():
    product = SimpleNamespace(
        status="active",
        compliance_level="normal",
        allow_proactive_push=True,
        merchant_recommendable=True,
        allow_partner_share=True,
    )
    assert allow_proactive_recommend(product) is True

    product.merchant_recommendable = False
    assert allow_proactive_recommend(product) is False


def test_partner_share_requires_normal_and_merchant_ok():
    product = SimpleNamespace(
        status="active",
        compliance_level="normal",
        allow_proactive_push=True,
        merchant_recommendable=True,
        allow_partner_share=True,
    )
    assert allow_partner_share(product) is True

    product.allow_partner_share = False
    assert allow_partner_share(product) is False


def test_user_search_allows_restricted_but_not_hard_block():
    restricted = SimpleNamespace(status="active", compliance_level="restricted")
    hard_block = SimpleNamespace(status="active", compliance_level="hard_block")
    assert allow_user_search_display(restricted) is True
    assert allow_user_search_display(hard_block) is False
