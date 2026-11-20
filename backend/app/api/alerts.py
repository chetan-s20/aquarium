from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import Alert, User
from app.schemas import AlertRead
from app.services.alerts import evaluate_device_offline
from app.services.audit import audit

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
def list_alerts(
    tank_id: str | None = None,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    evaluate_device_offline(db)
    q = db.query(Alert)
    if tank_id:
        q = q.filter(Alert.tank_id == tank_id)
    if status:
        q = q.filter(Alert.status == status)
    return q.order_by(Alert.triggered_at.desc()).limit(limit).all()


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
def acknowledge(
    alert_id: str,
    by: str = Query("operator", max_length=120),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")
    if alert.status == "open":  # resolved alerts stay resolved
        alert.status = "acknowledged"
    alert.acknowledged_by = by
    alert.acknowledged_at = datetime.now(timezone.utc)
    db.flush()
    audit(db, user.name, "acknowledge", "alert", alert.id, alert.status)
    db.commit()
    db.refresh(alert)
    return alert
