from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import Device, Reading, Sensor, Tank
from app.services.activity_limits import derive_activity_limits


def _setup(db, tank_id):
    db.add(Tank(id=tank_id, name=tank_id.replace("_", " ").title()))
    db.add(Device(id=f"syn-{tank_id}", tank_id=tank_id, name=f"{tank_id} cam",
                  device_type="camera", status="simulated"))
    for metric, unit in (("dissolved_oxygen", "mg/L"), ("fish_activity", "%")):
        db.add(Sensor(id=f"syn-{tank_id}-{metric}", device_id=f"syn-{tank_id}", tank_id=tank_id,
                      metric=metric, unit=unit, physical_min=0, physical_max=100))
    db.commit()


def _add_reading(db, tank_id, metric, value, ts):
    db.add(Reading(tank_id=tank_id, sensor_id=f"syn-{tank_id}-{metric}", metric=metric,
                   value=value, unit="mg/L" if metric == "dissolved_oxygen" else "%",
                   observed_at=ts, quality_status="valid"))


def test_derives_low_warning_from_five_low_do_events(client):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        _setup(db, "tank_al1")
        for i, v in enumerate([3.5, 3.6, 3.7, 3.8, 3.9]):
            ts = now - timedelta(hours=5 - i)
            _add_reading(db, "tank_al1", "dissolved_oxygen", v, ts)
            for _ in range(2):
                _add_reading(db, "tank_al1", "fish_activity", 0.3, ts)
        db.commit()
        prop = derive_activity_limits(db, "tank_al1")
    assert prop is not None
    assert prop["metric"] == "fish_activity" and prop["tank_id"] == "tank_al1"
    assert prop["low_events"] == 5
    assert prop["low_warning"] == 0.3


def test_no_proposal_without_five_low_do_events(client):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        _setup(db, "tank_al2")
        for i, v in enumerate([3.5, 3.6]):  # only 2 low-DO events
            ts = now - timedelta(hours=2 - i)
            _add_reading(db, "tank_al2", "dissolved_oxygen", v, ts)
            for _ in range(3):
                _add_reading(db, "tank_al2", "fish_activity", 0.2, ts)
        db.commit()
        assert derive_activity_limits(db, "tank_al2") is None


def test_no_proposal_without_activity_data(client):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        _setup(db, "tank_al3")
        for i in range(5):
            _add_reading(db, "tank_al3", "dissolved_oxygen", 3.5 + i * 0.01, now - timedelta(hours=5 - i))
        db.commit()
        assert derive_activity_limits(db, "tank_al3") is None
