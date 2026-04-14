from pathlib import Path

from app.services.product_poster_service import generate_product_poster_svg


def test_generate_product_poster_svg(tmp_path: Path):
    output = tmp_path / "poster.svg"
    result = generate_product_poster_svg(
        title="测试商品标题",
        shop_name="测试店铺",
        category_name="牙膏",
        price_text="¥19.90",
        reason_text="当前券后更便宜，适合直接看看",
        link_text="/api/promotion/redirect?wechat_openid=wx&product_id=1",
        badge_text="每日推荐",
        output_path=str(output),
    )
    assert result.endswith(".svg")
    assert output.exists()
    assert "测试商品标题" in output.read_text(encoding="utf-8")
