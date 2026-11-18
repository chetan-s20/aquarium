import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Security, UploadFile

from app.security import require_operator_key
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.importer import commit_import, validate_csv

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/preview")
async def preview(file: UploadFile = File(...), mapping: str | None = Form(None)):
    content = await file.read()
    mp = json.loads(mapping) if mapping else None
    result = validate_csv(content, mp)
    # do not return full rows in preview? keep summary + preview
    return {
        "filename": file.filename,
        "delimiter": result["delimiter"],
        "fieldnames": result["fieldnames"],
        "row_count": result["row_count"],
        "accepted_count": result["accepted_count"],
        "rejected_count": result["rejected_count"],
        "duplicate_count": result["duplicate_count"],
        "gap_count": result["gap_count"],
        "outlier_count": result["outlier_count"],
        "errors": result["errors"],
        "preview": result["preview"],
    }


@router.post("/commit")
async def commit(file: UploadFile = File(...), mapping: str | None = Form(None), db: Session = Depends(get_db), _key: str = Security(require_operator_key)):
    content = await file.read()
    mp = json.loads(mapping) if mapping else None
    run = commit_import(db, content, file.filename or "upload.csv", mp)
    return {
        "import_run_id": run.id,
        "status": run.status,
        "row_count": run.row_count,
        "accepted_count": run.accepted_count,
        "rejected_count": run.rejected_count,
        "duplicate_count": run.duplicate_count,
    }
