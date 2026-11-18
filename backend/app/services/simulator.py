import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Reading, Sensor
from app.services.alerts import evaluate_thresholds

PROFILES = {
    "temperature": (24.0, 1.2, 20.0, 28.0),
    "ph": (7.2, 0.15, 6.8, 7.8),
    "tds": (300.0, 25.0, 200.0, 450.0),
    "turbidity": (5.0, 2.0, 0.0, 15.0),
    "dissolved_oxygen": (7.5, 0.6, 6.0, 9.0),
}


def run_simulation(db: Session, tank_id: str, count: int = 24, interval_minutes: int = 5, seed: int = 42) -> int:
    rng = random.Random(seed)
    sensors = db.query(Sensor).filter(Sensor.tank_id == tank_id).all()
    if not sensors:
        return 0
    now = datetime.now(timezone.utc)
    inserted = 0
    for sensor in sensors:
        profile = PROFILES.get(sensor.metric, (10.0, 1.0, 0.0, 100.0))
        base, noise, lo, hi = profile
        for i in range(count):
            observed = now - timedelta(minutes=interval_minutes * i)
            if rng.random() < 0.05:
                value = None
            elif rng.random() < 0.03:
                value = hi + 5.0
            else:
                value = round(base + rng.uniform(-noise, noise), 3)
            quality = "missing" if value is None else ("invalid" if (value < lo or value > hi) else "valid")
            reading = Reading(
                id=str(uuid.uuid4()),
                tank_id=tank_id,
                device_id=sensor.device_id,
                sensor_id=sensor.id,
                metric=sensor.metric,
                value=value,
                unit=sensor.unit,
                observed_at=observed,
                quality_status=quality,
                quality_rule_version="simulator-v1",
                source="simulator",
                raw_payload={"simulated": True, "profile": profile},
            )
            db.add(reading)
            db.flush()
            evaluate_thresholds(db, reading)
            inserted += 1
    db.commit()
    return inserted
