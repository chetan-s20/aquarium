from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        env=settings.app_env,
        database="ok",
        simulation_mode=settings.simulation_mode,
    )
