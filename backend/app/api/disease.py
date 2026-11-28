"""Check a fish photo with the disease CNN (ml/disease_service.py). A hint for staff, not a diagnosis."""
import json
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth import require_user
from app.config import settings
from app.models import User

router = APIRouter(prefix="/disease", tags=["disease"])
MAX_BYTES = 10 * 1024 * 1024


def ask_model(photo: bytes) -> dict:
    """POST the photo to the checker service. Raises OSError when it can't be reached."""
    req = urllib.request.Request(f"{settings.disease_url.rstrip('/')}/predict", data=photo, method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 422:
            raise HTTPException(status_code=422, detail="That file is not a readable photo.")
        raise HTTPException(status_code=502, detail=f"The photo checker failed (HTTP {e.code}).")


@router.post("/check")
def check_photo(photo: UploadFile = File(...), _user: User = Depends(require_user)):
    """Top 3 likely conditions for one fish photo. Operators only, since it runs the model on uploads."""
    if not settings.disease_url:
        raise HTTPException(status_code=503, detail="The photo checker is not set up on this server.")
    if not (photo.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="Upload a photo (JPEG or PNG).")
    data = photo.file.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(status_code=422, detail="The photo is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="The photo is larger than 10 MB.")
    try:
        return ask_model(data)
    except OSError:
        raise HTTPException(status_code=503, detail="The photo checker is not running.")
