"""Plausible SIMULATED pond data. Every row it writes has source="simulator".

Models the daily oxygen cycle of a fed pond: algae photosynthesis pushes DO and pH up
through the afternoon, respiration pulls DO down overnight to a dawn low. Cloudy days
lower the curve, which is when dawn DO crosses the warning/critical limits. Fish
activity drops at night and surface activity (gasping) rises when DO is low.
"""
import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.catalog import METRICS
from app.config import settings
from app.models import Reading, Sensor
from app.services.alerts import evaluate_thresholds, thresholds_for
from app.services.quality import QUALITY_RULE_VERSION, evaluate_reading


def _values(t: datetime, rng: random.Random, day_offset: float, turbidity: float) -> dict[str, float]:
    local = t + timedelta(hours=settings.farm_utc_offset_hours)
    hour = local.hour + local.minute / 60
    cycle = math.sin(2 * math.pi * (hour - 10) / 24)  # peak ~16:00, low ~04:00
    daylight = max(0.0, math.sin(math.pi * (hour - 6) / 12))  # 0 at night, 1 at noon
    do = 6.6 + 2.6 * cycle + day_offset + rng.gauss(0, 0.15)
    hypoxia = max(0.0, 4.5 - do)
    return {
        "dissolved_oxygen": round(max(do, 0.3), 2),
        "temperature": round(29.0 + 1.6 * math.sin(2 * math.pi * (hour - 9) / 24) + rng.gauss(0, 0.1), 2),
        "ph": round(7.7 + 0.45 * cycle + rng.gauss(0, 0.04), 2),
        "turbidity": round(turbidity, 1),
        "fish_activity": round(max(0.2, 1.2 + 2.3 * daylight - 0.4 * hypoxia + rng.gauss(0, 0.2)), 2),
        "surface_activity": round(min(95.0, max(2.0, 12 + 14 * hypoxia + rng.gauss(0, 2))), 1),
    }


def run_simulation(db: Session, tank_id: str, hours: int = 24, interval_minutes: int = 10, seed: int | None = None) -> int:
    """Fill readings from the tank's last reading (or `hours` ago) up to now. Never duplicates."""
    sensors = {s.metric: s for s in db.query(Sensor).filter(Sensor.tank_id == tank_id) if s.metric in METRICS}
    if not sensors:
        return 0
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    step = timedelta(minutes=interval_minutes)
    last = db.query(func.max(Reading.observed_at)).filter(Reading.tank_id == tank_id).scalar()
    if last is not None and last.tzinfo is None:  # SQLite drops tzinfo
        last = last.replace(tzinfo=timezone.utc)
    t = max(last + step, now - timedelta(hours=hours)) if last else now - timedelta(hours=hours)

    thresholds = {m: thresholds_for(db, tank_id, m) for m in sensors}
    day_offset, day, turbidity, inserted = 0.0, None, 25.0, 0
    while t <= now:
        local_day = (t + timedelta(hours=settings.farm_utc_offset_hours)).date()
        if local_day != day:
            day = local_day
            day_offset = rng.choice([0.0, 0.0, 0.0, -0.8, -1.6, -2.4])  # some cloudy days
        turbidity = min(120.0, max(5.0, turbidity + 0.03 * (28 - turbidity) + rng.gauss(0, 1.2)))
        for metric, value in _values(t, rng, day_offset, turbidity).items():
            sensor = sensors.get(metric)
            if sensor is None:
                continue
            if rng.random() < 0.004:
                value = None  # dropped packet
            elif rng.random() < 0.002:
                value = sensor.physical_max + 5  # sensor glitch, gets marked invalid
            reading = Reading(
                tank_id=tank_id, device_id=sensor.device_id, sensor_id=sensor.id,
                metric=metric, value=value, unit=sensor.unit, observed_at=t,
                quality_status=evaluate_reading(value, sensor.physical_min, sensor.physical_max),
                quality_rule_version=QUALITY_RULE_VERSION, source="simulator",
                raw_value=value, raw_payload={"simulated": True},
            )
            db.add(reading)
            if thresholds.get(metric):
                evaluate_thresholds(db, reading, thresholds[metric])
            inserted += 1
        t += step
    db.commit()
    return inserted
