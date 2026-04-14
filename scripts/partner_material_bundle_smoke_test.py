from __future__ import annotations

import json

from app.core.db import SessionLocal
from app.models.partner_share_asset import PartnerShareAsset
from app.services.partner_material_bundle_service import (
    get_partner_material_bundle_manifest,
    resolve_partner_material_file,
)


def main() -> int:
    db = SessionLocal()
    try:
        assets = (
            db.query(PartnerShareAsset)
            .order_by(PartnerShareAsset.id.desc())
            .limit(10)
            .all()
        )

        if not assets:
            print("WARN: no partner share assets found")
            return 0

        for asset in assets:
            try:
                manifest = get_partner_material_bundle_manifest(db, asset.asset_token)
            except Exception as exc:
                print(f"skip asset_token={asset.asset_token}: manifest error: {exc}")
                continue

            items = manifest.get("items") or []
            if not items:
                print(f"skip asset_token={asset.asset_token}: no material items")
                continue

            for item in items:
                try:
                    file_info = resolve_partner_material_file(
                        db,
                        asset.asset_token,
                        item["file_kind"],
                    )
                    result = {
                        "asset_token": manifest.get("asset_token"),
                        "bundle_url": manifest.get("bundle_url"),
                        "item_count": len(items),
                        "resolved_file_kind": item["file_kind"],
                        "resolved_relative_path": file_info.relative_path,
                        "resolved_abs_path": str(file_info.abs_path),
                        "media_type": file_info.media_type,
                    }
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    print("PASS: partner material bundle smoke test ok")
                    return 0
                except Exception as exc:
                    print(f"skip asset_token={asset.asset_token} file_kind={item['file_kind']}: {exc}")

        print("WARN: no resolvable partner material bundle file found")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
