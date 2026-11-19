import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Security, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import require_operator_key
from app.services.importer import commit_import, validate_csv

router = APIRouter(prefix="/imports", tags=["imports"])
MAX_BYTES = 20 * 1024 * 1024


async def _read(file: UploadFile, mapping: str | None) -> tuple[bytes, dict | None]:
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="file larger than 20 MB; split it")
    try:
        mp = json.loads(mapping) if mapping else None
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="mapping must be JSON like {\"sensor_id\": \"Probe\"}")
    return content, mp


@router.post("/preview")
async def preview(file: UploadFile = File(...), mapping: str | None = Form(None)):
    content, mp = await _read(file, mapping)
    result = validate_csv(content, mp)
    result.pop("rows")
    return {"filename": file.filename, **result}


@router.post("/commit")
async def commit(
    file: UploadFile = File(...),
    mapping: str | None = Form(None),
    db: Session = Depends(get_db),
    _key: str = Security(require_operator_key),
):
    content, mp = await _read(file, mapping)
    run = commit_import(db, content, file.filename or "upload.csv", mp)
    return {
        "import_run_id": run.id,
        "status": run.status,
        "row_count": run.row_count,
        "accepted_count": run.accepted_count,
        "rejected_count": run.rejected_count,
        "duplicate_count": run.duplicate_count,
    }
