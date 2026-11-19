from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Device, Reading, Sensor
from app.schemas import ReadingCreate, ReadingRead, UTCDateTime
from app.security import require_device_key
from app.services.alerts import evaluate_thresholds
from app.services.quality import QUALITY_RULE_VERSION, evaluate_reading

router = APIRouter(prefix="/readings", tags=["readings"])


@router.post("", response_model=ReadingRead, status_code=201)
def create_reading(payload: ReadingCreate, db: Session = Depends(get_db), _key: str = Security(require_device_key)):
    sensor = db.get(Sensor, payload.sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="sensor not found")
    # NULL sequence_no defeats the DB unique constraint, so check duplicates here too
    dup = db.query(Reading.id).filter(
        Reading.sensor_id == sensor.id,
        Reading.observed_at == payload.observed_at,
        Reading.sequence_no.is_(None) if payload.sequence_no is None else Reading.sequence_no == payload.sequence_no,
    ).first()
    if dup:
        raise HTTPException(status_code=409, detail="reading already stored for this sensor and time")

    reading = Reading(
        tank_id=sensor.tank_id,
        device_id=sensor.device_id,
        sensor_id=sensor.id,
        metric=sensor.metric,
        value=payload.value,
        unit=sensor.unit,
        observed_at=payload.observed_at,
        sequence_no=payload.sequence_no,
        quality_status=evaluate_reading(payload.value, sensor.physical_min, sensor.physical_max),
        quality_rule_version=QUALITY_RULE_VERSION,
        calibration_id=payload.calibration_id,
        source=payload.source,
        raw_value=payload.raw_value if payload.raw_value is not None else payload.value,
        raw_payload=payload.raw_payload,
    )
    db.add(reading)
    device = db.get(Device, sensor.device_id)
    if device:
        device.last_seen_at = datetime.now(timezone.utc)
    evaluate_thresholds(db, reading)
    db.commit()
    db.refresh(reading)
    return reading


@router.get("", response_model=list[ReadingRead])
def list_readings(
    tank_id: str | None = None,
    sensor_id: str | None = None,
    metric: list[str] | None = Query(None),
    start: UTCDateTime | None = None,
    end: UTCDateTime | None = None,
    limit: int = Query(5000, ge=1, le=20000),
    db: Session = Depends(get_db),
):
    """Newest `limit` readings in the window, returned oldest-first (ready to chart)."""
    q = db.query(Reading)
    if tank_id:
        q = q.filter(Reading.tank_id == tank_id)
    if sensor_id:
        q = q.filter(Reading.sensor_id == sensor_id)
    if metric:
        q = q.filter(Reading.metric.in_(metric))
    if start:
        q = q.filter(Reading.observed_at >= start)
    if end:
        q = q.filter(Reading.observed_at <= end)
    return q.order_by(Reading.observed_at.desc()).limit(limit).all()[::-1]
