from app.services.product_intent_service import parse_product_intent


def test_parse_shopping_intent():
    result = parse_product_intent("买一包夜用苏菲卫生巾，想要更划算一点")
    assert result["shopping_intent"] is True
    assert result["commodity"] == "卫生巾"
    assert "夜用" in result["attribute_tokens"]
    assert result["wants_low_price"] is True
    assert any("苏菲" in token or "卫生巾" in token for token in result["search_tokens"])


def test_parse_nonshopping_intent():
    result = parse_product_intent("你是谁")
    assert result["shopping_intent"] is False
