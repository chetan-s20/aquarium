import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, engine, Base
from app.models import Tank, Device, Sensor, Reading

Base.metadata.create_all(bind=engine)


def seed():
    db: Session = SessionLocal()
    try:
        tank_id = "tank-demo-1"
        device_id = "device-demo-1"
        if not db.get(Tank, tank_id):
            db.add(Tank(id=tank_id, name="Demo Tank 1", species="UNCONFIRMED (provisional)", life_stage="UNCONFIRMED", volume_liters=100.0))
        if not db.get(Device, device_id):
            db.add(Device(id=device_id, tank_id=tank_id, name="Demo Gateway", device_type="simulated_gateway", firmware_version="0.0.0-sim", status="simulated"))
        sensor_defs = [
            ("sensor-temp-1", "temperature", "degC", 0.0, 45.0),
            ("sensor-ph-1", "ph", "pH", 0.0, 14.0),
            ("sensor-tds-1", "tds", "ppm", 0.0, 2000.0),
            ("sensor-turbidity-1", "turbidity", "NTU", 0.0, 1000.0),
            ("sensor-do-1", "dissolved_oxygen", "mg/L", 0.0, 20.0),
        ]
        for sid, metric, unit, lo, hi in sensor_defs:
            if not db.get(Sensor, sid):
                db.add(Sensor(id=sid, device_id=device_id, tank_id=tank_id, metric=metric, unit=unit, physical_min=lo, physical_max=hi, status="simulated"))
        db.commit()

        now = datetime.now(timezone.utc)
        for sid, metric, unit, lo, hi in sensor_defs:
            for i in range(12):
                observed = now - timedelta(minutes=5 * i)
                value = (lo + hi) / 2.0
                db.add(Reading(
                    id=str(uuid.uuid4()),
                    tank_id=tank_id,
                    device_id=device_id,
                    sensor_id=sid,
                    metric=metric,
                    value=value,
                    unit=unit,
                    observed_at=observed,
                    quality_status="valid",
                    quality_rule_version="phase1-placeholder",
                    source="simulator",
                    raw_payload={"note": "SIMULATED seed data - not a real measurement"},
                ))
        db.commit()
        print("Seeded demo data (SIMULATED).")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
