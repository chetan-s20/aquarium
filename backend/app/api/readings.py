from fastapi import APIRouter, Depends, HTTPException, Security

from app.security import require_device_key
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Reading, Sensor, Tank
from app.schemas import ReadingCreate, ReadingRead
from app.services.alerts import evaluate_thresholds
from app.services.quality import evaluate_reading

router = APIRouter(prefix="/readings", tags=["readings"])


@router.post("", response_model=ReadingRead, status_code=201)
def create_reading(payload: ReadingCreate, db: Session = Depends(get_db), _key: str = Security(require_device_key)):
    tank = db.get(Tank, payload.tank_id)
    if not tank:
        raise HTTPException(status_code=404, detail="tank not found")
    sensor = db.get(Sensor, payload.sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="sensor not found")

    status = evaluate_reading(payload.value, sensor.physical_min, sensor.physical_max)
    if payload.quality_status and payload.quality_status != "unknown":
        status = payload.quality_status

    reading = Reading(
        tank_id=payload.tank_id,
        device_id=payload.device_id,
        sensor_id=payload.sensor_id,
        metric=payload.metric,
        value=payload.value,
        unit=payload.unit,
        observed_at=payload.observed_at,
        sequence_no=payload.sequence_no,
        quality_status=status,
        quality_rule_version="phase2-range-v1",
        calibration_id=payload.calibration_id,
        source=payload.source,
        raw_value=payload.raw_value if payload.raw_value is not None else payload.value,
        raw_payload=payload.raw_payload,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    evaluate_thresholds(db, reading)
    return reading


@router.get("", response_model=list[ReadingRead])
def list_readings(
    tank_id: str | None = None,
    sensor_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(Reading)
    if tank_id:
        q = q.filter(Reading.tank_id == tank_id)
    if sensor_id:
        q = q.filter(Reading.sensor_id == sensor_id)
    return q.order_by(Reading.observed_at.desc()).limit(min(limit, 1000)).all()
