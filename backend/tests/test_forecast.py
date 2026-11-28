import math
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db import SessionLocal
from app.models import Device, Reading, Sensor, Tank
from app.services.forecast import dawn_do_forecast

# 20:30 farm time on a fixed day, so the tests don't depend on when they run
NOW = datetime(2026, 10, 1, 20, 30, tzinfo=timezone.utc) - timedelta(hours=settings.farm_utc_offset_hours)
LAST_DAWN = NOW - timedelta(hours=16, minutes=30)  # 04:00 farm time today


def _setup(db, tank_id):
    db.add(Tank(id=tank_id, name=tank_id.replace("_", " ").title()))
    db.flush()  # PostgreSQL checks foreign keys row by row: parents first
    db.add(Device(id=f"syn-{tank_id}", tank_id=tank_id, name=f"{tank_id} probe",
                  device_type="water_probe", status="simulated"))
    db.flush()
    db.add(Sensor(id=f"syn-{tank_id}-dissolved_oxygen", device_id=f"syn-{tank_id}",
                  tank_id=tank_id, metric="dissolved_oxygen", unit="mg/L",
                  physical_min=0, physical_max=20))
    db.commit()


def _pond(db, tank_id, hours: float, drop_after=None, drop=0.0):
    """Daily DO cycle (peak 16:00, low 4.0 mg/L at 04:00 farm time), every 10 min up to NOW.
    From `drop_after` on, the whole curve is `drop` mg/L lower (a cloudy day)."""
    t = NOW - timedelta(hours=hours)
    while t <= NOW:
        local = t + timedelta(hours=settings.farm_utc_offset_hours)
        h = local.hour + local.minute / 60
        v = 6.6 + 2.6 * math.sin(2 * math.pi * (h - 10) / 24) - (drop if drop_after and t >= drop_after else 0)
        db.add(Reading(tank_id=tank_id, sensor_id=f"syn-{tank_id}-dissolved_oxygen", metric="dissolved_oxygen",
                       value=round(v, 3), unit="mg/L", observed_at=t, quality_status="valid"))
        t += timedelta(minutes=10)
    db.commit()


def test_same_weather_forecasts_last_nights_low(client):
    with SessionLocal() as db:
        _setup(db, "tank_fc1")
        _pond(db, "tank_fc1", hours=40)
        f = dawn_do_forecast(db, "tank_fc1", now=NOW)
    assert f is not None and abs(f - 4.0) < 0.1


def test_cloudy_day_lowers_tonights_forecast(client):
    with SessionLocal() as db:
        _setup(db, "tank_fc2")
        # since an hour after last dawn, DO runs 1.5 mg/L below yesterday: tonight's low should be too
        _pond(db, "tank_fc2", hours=40, drop_after=LAST_DAWN + timedelta(hours=1), drop=1.5)
        f = dawn_do_forecast(db, "tank_fc2", now=NOW)
    assert f is not None and abs(f - 2.5) < 0.1


def test_no_forecast_without_a_day_of_history(client):
    with SessionLocal() as db:
        _setup(db, "tank_fc3")
        _pond(db, "tank_fc3", hours=12)
        assert dawn_do_forecast(db, "tank_fc3", now=NOW) is None
