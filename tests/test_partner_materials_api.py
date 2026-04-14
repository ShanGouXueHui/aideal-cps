from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
import app.api.partner_materials as api_mod


def test_partner_material_bundle_api(monkeypatch):
    monkeypatch.setattr(
        api_mod,
        "get_partner_material_bundle_manifest",
        lambda db, asset_token: {
            "asset_token": asset_token,
            "bundle_url": f"http://8.136.28.6/api/partner/materials/{asset_token}",
            "items": [
                {
                    "file_kind": "poster",
                    "relative_path": "data/demo/poster.svg",
                    "view_url": f"http://8.136.28.6/api/partner/materials/{asset_token}/files/poster",
                }
            ],
        },
    )

    client = TestClient(app)
    resp = client.get("/api/partner/materials/asset_demo_001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_token"] == "asset_demo_001"
    assert len(data["items"]) == 1


def test_partner_material_file_api(tmp_path, monkeypatch):
    poster = tmp_path / "poster.svg"
    poster.write_text("<svg/>", encoding="utf-8")

    monkeypatch.setattr(
        api_mod,
        "resolve_partner_material_file",
        lambda db, asset_token, file_kind: SimpleNamespace(
            abs_path=poster,
            media_type="image/svg+xml",
            filename="poster.svg",
        ),
    )

    client = TestClient(app)
    resp = client.get("/api/partner/materials/asset_demo_001/files/poster")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
