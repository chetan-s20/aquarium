from typing import Optional

from sqlalchemy.orm import Session

from app.models import Alert, Reading, Threshold


def _severity(value: float, t: Threshold, margin: float = 0.0) -> Optional[str]:
    """margin widens the warning band; used so an alert only resolves once the value clears it."""
    if t.low_critical is not None and value <= t.low_critical:
        return "critical"
    if t.high_critical is not None and value >= t.high_critical:
        return "critical"
    if t.low_warning is not None and value <= t.low_warning + margin:
        return "warning"
    if t.high_warning is not None and value >= t.high_warning - margin:
        return "warning"
    return None


def thresholds_for(db: Session, tank_id: str, metric: str) -> Optional[Threshold]:
    """Tank-specific threshold wins over a global (tank_id NULL) one."""
    rows = db.query(Threshold).filter(Threshold.metric == metric).filter(
        (Threshold.tank_id == tank_id) | (Threshold.tank_id.is_(None))
    ).all()
    return next((t for t in rows if t.tank_id == tank_id), rows[0] if rows else None)


def evaluate_thresholds(db: Session, reading: Reading, threshold: Optional[Threshold] = None) -> Optional[Alert]:
    """One alert per sensor at a time: open -> (escalate) -> resolved when value recovers.

    Caller commits. `threshold` may be passed to skip the lookup in bulk loops.
    """
    if reading.value is None or reading.quality_status != "valid":
        return None
    t = threshold or thresholds_for(db, reading.tank_id, reading.metric)
    if t is None:
        return None

    active = (
        db.query(Alert)
        .filter(Alert.sensor_id == reading.sensor_id, Alert.resolved_at.is_(None))
        .order_by(Alert.triggered_at.desc())
        .first()
    )
    sev = _severity(reading.value, t)

    if active:
        if sev == "critical" and active.severity == "warning":
            active.severity = "critical"
            active.value = reading.value
            active.reason = _reason(reading, "critical", t)
        elif _severity(reading.value, t, margin=t.hysteresis or 0.0) is None:
            active.status = "resolved"
            active.resolved_at = reading.observed_at
        db.flush()  # sessions don't autoflush; the next lookup must see this change
        return active

    if not sev:
        return None
    alert = Alert(
        tank_id=reading.tank_id,
        sensor_id=reading.sensor_id,
        metric=reading.metric,
        severity=sev,
        status="open",
        value=reading.value,
        threshold_id=t.id,
        reason=_reason(reading, sev, t),
        source="rule",
        triggered_at=reading.observed_at,
    )
    db.add(alert)
    db.flush()
    return alert


def _reason(r: Reading, sev: str, t: Threshold) -> str:
    low = t.low_critical if sev == "critical" else t.low_warning
    high = t.high_critical if sev == "critical" else t.high_warning
    side = f"below {low}" if low is not None and r.value <= low else f"above {high}"
    return f"{r.metric.replace('_', ' ')} {r.value:g} {r.unit} is {side} ({sev} limit)"
