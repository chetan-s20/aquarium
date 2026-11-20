from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Alert, Device, Reading, Threshold


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


def evaluate_device_offline(db: Session, now: Optional[datetime] = None) -> list[Alert]:
    """Open one warning alert per device that stopped reporting past the offline window.

    Devices post readings every 1–5 min (Phase 3); longer silence means the gateway
    is down or the link is lost. Demo devices (status "simulated") never report by
    design, so they are skipped.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=settings.device_offline_minutes)
    opened = []
    for d in db.query(Device).order_by(Device.id):
        if d.status == "simulated":
            continue
        seen = d.last_seen_at or d.created_at
        if seen is not None and seen.tzinfo is None:  # SQLite drops tzinfo on read
            seen = seen.replace(tzinfo=timezone.utc)
        if seen is not None and seen >= cutoff:
            continue
        if db.query(Alert).filter(Alert.device_id == d.id, Alert.status.in_(["open", "acknowledged"])).first():
            continue
        alert = Alert(
            tank_id=d.tank_id, device_id=d.id, metric="device_offline",
            severity="warning", status="open", value=None,
            reason=f"device {d.name} has not reported for {settings.device_offline_minutes} min",
            source="rule", triggered_at=now,
        )
        db.add(alert)
        opened.append(alert)
    if opened:
        db.commit()
    return opened


def resolve_device_alerts(db: Session, device_id: Optional[str], now: Optional[datetime] = None) -> int:
    """Close the device-offline alert when the device reports again (on the reading's arrival)."""
    if not device_id:
        return 0
    now = now or datetime.now(timezone.utc)
    closed = 0
    for a in db.query(Alert).filter(Alert.device_id == device_id, Alert.status.in_(["open", "acknowledged"])):
        a.status = "resolved"
        a.resolved_at = now
        closed += 1
    if closed:
        db.commit()
    return closed
