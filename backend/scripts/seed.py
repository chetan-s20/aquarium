"""Create demo tanks, devices, sensors, thresholds and a week of SIMULATED readings.

Run after `alembic upgrade head`:  python scripts/seed.py [--hours 168]
Safe to re-run: existing rows are kept and readings are only topped up to now.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session  # noqa: E402

from app.auth import hash_password
from app.catalog import METRICS  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Device, Sensor, Tank, Threshold, User  # noqa: E402
from app.services.fish_simulator import simulate_fish  # noqa: E402
from app.services.simulator import run_simulation  # noqa: E402

TANKS = [
    # Species are placeholders until the farm confirms stocking.
    # Camera tracking of individual fish needs clear water and a camera that sees the whole tank,
    # so the demo uses indoor tanks. length/depth = the area the side camera sees.
    dict(id="tank-a", name="Tank A", species="Rohu fingerlings (provisional)", life_stage="nursery",
         volume_liters=600, location="Hatchery shed", length_cm=150, depth_cm=60),
    dict(id="tank-b", name="Tank B", species="Catla fingerlings (provisional)", life_stage="nursery",
         volume_liters=450, location="Hatchery shed", length_cm=120, depth_cm=55),
]

# How far a value must recover past the warning limit before an alert closes (stops flapping).
HYSTERESIS = {"dissolved_oxygen": 0.3, "temperature": 0.5, "ph": 0.1, "turbidity": 5.0}


def seed(db: Session, hours: int = 168, fish_hours: int = 48) -> int:
    if not db.query(User).filter_by(name="operator").first():
        db.add(User(name="operator",
                    password_hash=hash_password(settings.operator_password, salt="operator"),
                    role="operator"))
        db.commit()
    for metric, spec in METRICS.items():
        if spec["thresholds"] and not db.query(Threshold).filter_by(metric=metric, tank_id=None).first():
            lc, lw, hw, hc = spec["thresholds"]
            db.add(Threshold(
                metric=metric, low_critical=lc, low_warning=lw, high_warning=hw, high_critical=hc,
                hysteresis=HYSTERESIS[metric],
                source="provisional - confirm per species", reference=spec["reference"],
            ))
    for t in TANKS:
        if not db.get(Tank, t["id"]):
            db.add(Tank(**t))
        for kind, dtype in (("water", "water_probe"), ("camera", "camera")):
            did = f"{t['id']}-{kind}"
            if not db.get(Device, did):
                db.add(Device(id=did, tank_id=t["id"], name=f"{t['name']} {kind}", device_type=dtype, status="simulated"))
        for metric, spec in METRICS.items():
            sid = f"{t['id']}-{metric}"
            if not db.get(Sensor, sid):
                db.add(Sensor(
                    id=sid, device_id=f"{t['id']}-{spec['source']}", tank_id=t["id"], metric=metric,
                    unit=spec["unit"], physical_min=spec["physical"][0], physical_max=spec["physical"][1],
                    sampling_interval_seconds=600, status="simulated",
                ))
    db.commit()
    n = sum(run_simulation(db, t["id"], hours=hours, seed=i) for i, t in enumerate(TANKS))
    for i, t in enumerate(TANKS):
        simulate_fish(db, t["id"], hours=fish_hours, seed=i)
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hours", type=int, default=168)
    args = ap.parse_args()
    with SessionLocal() as session:
        n = seed(session, args.hours)
    print(f"Seeded demo tanks; inserted {n} SIMULATED readings and 48 h of SIMULATED fish positions.")
