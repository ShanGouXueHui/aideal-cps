from app.services.product_compliance_service import classify_product_compliance


def test_classify_hard_block_product():
    result = classify_product_compliance(
        title="佐罗防狼雾剂女性防身用品",
        category_name="自驾野营",
        shop_name="测试店铺",
        forbid_types=[0],
    )
    assert result["compliance_level"] == "hard_block"
    assert result["allow_proactive_push"] is False
    assert result["allow_partner_share"] is False


def test_classify_restricted_product():
    result = classify_product_compliance(
        title="成人情趣跳蛋震动棒",
        category_name="成人用品",
        shop_name="测试店铺",
        forbid_types=[0],
    )
    assert result["compliance_level"] == "restricted"
    assert result["age_gate_required"] is True
    assert result["allow_proactive_push"] is False
    assert result["allow_partner_share"] is False


def test_classify_normal_product():
    result = classify_product_compliance(
        title="家用洗衣液组合装",
        category_name="衣物清洁",
        shop_name="测试店铺",
        forbid_types=[0],
    )
    assert result["compliance_level"] == "normal"
    assert result["allow_proactive_push"] is True
    assert result["allow_partner_share"] is True
