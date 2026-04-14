from pathlib import Path
from types import SimpleNamespace

from app.services import partner_material_bundle_service as svc


def test_get_partner_material_bundle_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "PROJECT_ROOT", tmp_path)

    poster = tmp_path / "data" / "demo" / "poster.svg"
    buy_qr = tmp_path / "data" / "demo" / "buy_qr.svg"
    share_qr = tmp_path / "data" / "demo" / "share_qr.svg"
    poster.parent.mkdir(parents=True, exist_ok=True)
    poster.write_text("<svg/>", encoding="utf-8")
    buy_qr.write_text("<svg/>", encoding="utf-8")
    share_qr.write_text("<svg/>", encoding="utf-8")

    monkeypatch.setattr(
        svc,
        "_get_asset_by_token",
        lambda db, asset_token: SimpleNamespace(
            asset_token="asset_demo_001",
            partner_code="pc_demo_001",
            partner_account_id=1,
            product_id=4,
            title="维达卷纸超值装",
            buy_url="http://8.136.28.6/api/partner/assets/demo/buy",
            share_url="http://8.136.28.6/api/partner/assets/demo/share",
            buy_copy="购买文案",
            share_copy="分享文案",
            poster_svg_path="data/demo/poster.svg",
            buy_qr_svg_path="data/demo/buy_qr.svg",
            share_qr_svg_path="data/demo/share_qr.svg",
        ),
    )

    result = svc.get_partner_material_bundle_manifest(None, "asset_demo_001")
    assert result["asset_token"] == "asset_demo_001"
    assert len(result["items"]) == 3
    assert result["bundle_url"].endswith("/api/partner/materials/asset_demo_001")


def test_resolve_partner_material_file(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "PROJECT_ROOT", tmp_path)

    poster = tmp_path / "data" / "demo" / "poster.svg"
    poster.parent.mkdir(parents=True, exist_ok=True)
    poster.write_text("<svg/>", encoding="utf-8")

    monkeypatch.setattr(
        svc,
        "_get_asset_by_token",
        lambda db, asset_token: SimpleNamespace(
            asset_token="asset_demo_001",
            poster_svg_path="data/demo/poster.svg",
            buy_qr_svg_path=None,
            share_qr_svg_path=None,
        ),
    )

    file_info = svc.resolve_partner_material_file(None, "asset_demo_001", "poster")
    assert file_info.relative_path == "data/demo/poster.svg"
    assert file_info.media_type == "image/svg+xml"
    assert Path(file_info.abs_path).exists()
