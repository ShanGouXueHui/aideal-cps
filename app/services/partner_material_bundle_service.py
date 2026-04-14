from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.models.partner_share_asset import PartnerShareAsset
from app.services.partner_material_bundle_config_service import load_partner_material_bundle_rules


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _get_asset_by_token(db, asset_token: str):
    return db.query(PartnerShareAsset).filter(PartnerShareAsset.asset_token == asset_token).first()


def _resolve_relative_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    return str(path_value).strip()


def _resolve_abs_path(relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        abs_path = path
    else:
        abs_path = (PROJECT_ROOT / path).resolve()

    project_root = PROJECT_ROOT.resolve()
    if project_root not in abs_path.parents and abs_path != project_root:
        raise ValueError("material path escapes project root")
    return abs_path


def _guess_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".png":
        return "image/png"
    if suffix == ".jpg" or suffix == ".jpeg":
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"


def get_partner_material_bundle_manifest(db, asset_token: str) -> dict:
    rules = load_partner_material_bundle_rules()
    base_url = (rules.get("base_url") or "").rstrip("/")
    file_kind_map = rules.get("file_kind_map") or {}

    asset = _get_asset_by_token(db, asset_token)
    if not asset:
        raise ValueError("partner asset not found")

    items: list[dict] = []
    for file_kind, attr_name in file_kind_map.items():
        relative_path = _resolve_relative_path(getattr(asset, attr_name, None))
        if not relative_path:
            continue
        items.append(
            {
                "file_kind": file_kind,
                "relative_path": relative_path,
                "view_url": f"{base_url}/api/partner/materials/{asset_token}/files/{file_kind}",
            }
        )

    return {
        "asset_token": asset.asset_token,
        "partner_code": getattr(asset, "partner_code", None),
        "partner_account_id": getattr(asset, "partner_account_id", None),
        "product_id": getattr(asset, "product_id", None),
        "title": getattr(asset, "title", None),
        "buy_url": getattr(asset, "buy_url", None),
        "share_url": getattr(asset, "share_url", None),
        "buy_copy": getattr(asset, "buy_copy", None),
        "share_copy": getattr(asset, "share_copy", None),
        "bundle_url": f"{base_url}/api/partner/materials/{asset_token}",
        "items": items,
    }


def resolve_partner_material_file(db, asset_token: str, file_kind: str) -> SimpleNamespace:
    rules = load_partner_material_bundle_rules()
    file_kind_map = rules.get("file_kind_map") or {}

    attr_name = file_kind_map.get(file_kind)
    if not attr_name:
        raise ValueError("unsupported material file kind")

    asset = _get_asset_by_token(db, asset_token)
    if not asset:
        raise ValueError("partner asset not found")

    relative_path = _resolve_relative_path(getattr(asset, attr_name, None))
    if not relative_path:
        raise ValueError("material file path missing")

    abs_path = _resolve_abs_path(relative_path)
    if not abs_path.exists():
        raise FileNotFoundError(str(abs_path))

    return SimpleNamespace(
        asset=asset,
        file_kind=file_kind,
        relative_path=relative_path,
        abs_path=abs_path,
        media_type=_guess_media_type(abs_path),
        filename=abs_path.name,
    )
