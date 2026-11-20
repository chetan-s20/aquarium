from datetime import datetime, timedelta, timezone

import pytest

from app.db import SessionLocal
from app.models import Device, Reading, Sensor, Tank
from app.services.forecast import dawn_do_forecast


def _setup(db, tank_id):
    db.add(Tank(id=tank_id, name=tank_id.replace("_", " ").title()))
    db.add(Device(id=f"syn-{tank_id}", tank_id=tank_id, name=f"{tank_id} probe",
                  device_type="water_probe", status="simulated"))
    db.add(Sensor(id=f"syn-{tank_id}-dissolved_oxygen", device_id=f"syn-{tank_id}",
                  tank_id=tank_id, metric="dissolved_oxygen", unit="mg/L",
                  physical_min=0, physical_max=10))
    db.commit()


def _add_reading(db, tank_id, value, ts):
    db.add(Reading(tank_id=tank_id, sensor_id=f"syn-{tank_id}-dissolved_oxygen",
                   metric="dissolved_oxygen", value=value, unit="mg/L",
                   observed_at=ts, quality_status="valid"))


def test_forecast_below_current_for_declining_trend(client):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        _setup(db, "tank_fc1")
        # DO declines 1 mg/L per hour through "now": 12 at -4h ... 8 at now
        for i in range(5):
            _add_reading(db, "tank_fc1", 12 - i, now - timedelta(hours=4 - i))
        db.commit()
        f = dawn_do_forecast(db, "tank_fc1", now=now)
    assert f is not None and f < 8


def test_forecast_near_current_for_flat_trend(client):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        _setup(db, "tank_fc2")
        for i in range(6):
            _add_reading(db, "tank_fc2", 7.0, now - timedelta(hours=6 - i))
        db.commit()
        f = dawn_do_forecast(db, "tank_fc2", now=now)
    assert f is not None and abs(f - 7.0) < 0.01


def test_forecast_none_without_enough_data(client):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        _setup(db, "tank_fc3")
        _add_reading(db, "tank_fc3", 7.0, now - timedelta(hours=1))
        db.commit()
        assert dawn_do_forecast(db, "tank_fc3", now=now) is None
