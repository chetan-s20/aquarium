"""Retention policy (Phase 6): optionally delete readings older than RETENTION_DAYS."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Reading


def delete_expired_readings(db: Session, now: Optional[datetime] = None) -> int:
    """Delete readings with observed_at older than RETENTION_DAYS; 0 disables it. Returns the count."""
    if settings.retention_days <= 0:
        return 0
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.retention_days)
    n = db.query(Reading).filter(Reading.observed_at < cutoff).delete(synchronize_session=False)
    db.commit()
    return n
