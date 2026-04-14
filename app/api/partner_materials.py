from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.partner_material_bundle_service import (
    get_partner_material_bundle_manifest,
    resolve_partner_material_file,
)

router = APIRouter(prefix="/api/partner/materials", tags=["partner-materials"])


@router.get("/{asset_token}")
def get_partner_material_bundle(asset_token: str, db: Session = Depends(get_db)):
    try:
        return get_partner_material_bundle_manifest(db, asset_token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{asset_token}/files/{file_kind}")
def get_partner_material_file(asset_token: str, file_kind: str, db: Session = Depends(get_db)):
    try:
        file_info = resolve_partner_material_file(db, asset_token, file_kind)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        path=str(file_info.abs_path),
        media_type=file_info.media_type,
        filename=file_info.filename,
    )
