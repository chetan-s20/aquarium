from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Security

from app.security import require_operator_key
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Alert

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def list_alerts(status: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(Alert)
    if status:
        q = q.filter(Alert.status == status)
    return q.order_by(Alert.triggered_at.desc()).limit(min(limit, 500)).all()


@router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: str, by: str = "operator", db: Session = Depends(get_db), _key: str = Security(require_operator_key)):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.status = "acknowledged"
    alert.acknowledged_by = by
    alert.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert
