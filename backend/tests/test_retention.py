from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db import SessionLocal
from app.models import Device, Reading, Sensor, Tank
from app.services.retention import delete_expired_readings


def test_retention_deletes_readings_older_than_retention_days(client, monkeypatch):
    monkeypatch.setattr(settings, "retention_days", 30)
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(Tank(id="tank_rt", name="Tank RT"))
        db.flush()  # PostgreSQL checks foreign keys row by row: parents first
        db.add(Device(id="syn-rt", tank_id="tank_rt", name="r", device_type="sensor", status="simulated"))
        db.flush()
        db.add(Sensor(id="syn-rt-dissolved_oxygen", device_id="syn-rt", tank_id="tank_rt",
                      metric="dissolved_oxygen", unit="mg/L"))
        db.commit()
        db.add(Reading(tank_id="tank_rt", sensor_id="syn-rt-dissolved_oxygen", metric="dissolved_oxygen",
                       value=7.0, unit="mg/L", observed_at=now - timedelta(days=31), quality_status="valid"))
        db.add(Reading(tank_id="tank_rt", sensor_id="syn-rt-dissolved_oxygen", metric="dissolved_oxygen",
                       value=7.1, unit="mg/L", observed_at=now - timedelta(days=5), quality_status="valid"))
        db.commit()
        n = delete_expired_readings(db)
    assert n >= 1
    with SessionLocal() as db:
        assert not db.query(Reading).filter_by(tank_id="tank_rt", value=7.0).all()
        assert db.query(Reading).filter_by(tank_id="tank_rt", value=7.1).count() == 1
