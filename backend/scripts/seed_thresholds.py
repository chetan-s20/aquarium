import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.orm import Session

from app.db import SessionLocal, Base, engine
from app.models import Threshold, Tank

Base.metadata.create_all(bind=engine)

THRESHOLDS = [
    ("temperature", 18.0, 20.0, 28.0, 30.0, "degC"),
    ("ph", 6.0, 6.5, 8.5, 9.0, "pH"),
    ("tds", None, 200.0, 500.0, 600.0, "ppm"),
    ("turbidity", None, None, 20.0, 40.0, "NTU"),
    ("dissolved_oxygen", 4.0, 5.0, None, None, "mg/L"),
]


def seed():
    db: Session = SessionLocal()
    try:
        tank = db.query(Tank).first()
        if not tank:
            print("No tank found; run seed_demo.py first.")
            return
        for metric, lc, lw, hw, hc, unit in THRESHOLDS:
            exists = db.query(Threshold).filter(Threshold.tank_id == tank.id, Threshold.metric == metric).first()
            if exists:
                continue
            db.add(Threshold(
                tank_id=tank.id,
                metric=metric,
                low_critical=lc,
                low_warning=lw,
                high_warning=hw,
                high_critical=hc,
                hysteresis=0.5,
                cooldown_seconds=300,
                source="PROVISIONAL PLACEHOLDER - NOT FOR OPERATIONAL USE",
                reference="config/sensors.example.yaml",
                uncertainty="unconfirmed",
            ))
        db.commit()
        print("Seeded provisional thresholds (NOT operational).")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
