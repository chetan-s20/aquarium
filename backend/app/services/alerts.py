from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Alert, Reading, Threshold


def _severity(value: float, t: Threshold) -> Optional[str]:
    if t.low_critical is not None and value <= t.low_critical:
        return "critical"
    if t.high_critical is not None and value >= t.high_critical:
        return "critical"
    if t.low_warning is not None and value <= t.low_warning:
        return "warning"
    if t.high_warning is not None and value >= t.high_warning:
        return "warning"
    return None


def evaluate_thresholds(db: Session, reading: Reading) -> Optional[Alert]:
    if reading.value is None:
        return None
    thresholds = (
        db.query(Threshold)
        .filter(Threshold.metric == reading.metric)
        .filter((Threshold.tank_id == reading.tank_id) | (Threshold.tank_id.is_(None)))
        .all()
    )
    for t in thresholds:
        sev = _severity(reading.value, t)
        if not sev:
            continue
        cooldown = t.cooldown_seconds or 300
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown)
        existing = (
            db.query(Alert)
            .filter(Alert.sensor_id == reading.sensor_id)
            .filter(Alert.metric == reading.metric)
            .filter(Alert.status == "open")
            .first()
        )
        if existing:
            return existing
        recent = (
            db.query(Alert)
            .filter(Alert.sensor_id == reading.sensor_id)
            .filter(Alert.metric == reading.metric)
            .filter(Alert.triggered_at >= cutoff)
            .first()
        )
        if recent:
            return None
        alert = Alert(
            tank_id=reading.tank_id,
            sensor_id=reading.sensor_id,
            metric=reading.metric,
            severity=sev,
            status="open",
            value=reading.value,
            threshold_id=t.id,
            reason=f"{reading.metric} value {reading.value} {reading.unit} breached {sev} threshold (source={t.source})",
            source="rule",
            triggered_at=reading.observed_at,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert
    return None
