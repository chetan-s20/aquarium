"""Forecast tonight's pre-dawn dissolved oxygen (Phase 5).

Persistence + anomaly, a standard baseline for daily cycles: tonight's dawn low = last night's dawn
low, shifted by how much DO now differs from the same time yesterday. A cloudy day (less
photosynthesis) lowers the whole curve, so it lowers the forecast too. Works at any hour, needs about
a day of readings. Not yet validated on real nights (plan §7, Phase 5); no weather input yet.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Reading

DAWN_HOUR = 4.0  # farm-local hour of the pre-dawn DO low
WINDOW = timedelta(minutes=30)  # same trailing window for every lookup, so slopes don't bias the comparison


def _do_before(db: Session, tank_id: str, t: datetime) -> Optional[float]:
    """Mean valid DO in the WINDOW up to t, or None if there is none."""
    vals = [v for (v,) in db.query(Reading.value).filter(
        Reading.tank_id == tank_id,
        Reading.metric == "dissolved_oxygen",
        Reading.quality_status == "valid",
        Reading.value.isnot(None),
        Reading.observed_at.between(t - WINDOW, t),
    )]
    return sum(vals) / len(vals) if vals else None


def next_dawn(now: datetime) -> datetime:
    local = now + timedelta(hours=settings.farm_utc_offset_hours)
    return now + timedelta(hours=(DAWN_HOUR - local.hour - local.minute / 60) % 24)


def dawn_do_forecast(db: Session, tank_id: str, now: Optional[datetime] = None) -> Optional[float]:
    """DO forecast for the next local dawn, or None without readings at last dawn, now and 24 h ago."""
    now = now or datetime.now(timezone.utc)
    last_dawn = next_dawn(now) - timedelta(days=1)
    dawn_do, today, yesterday = (_do_before(db, tank_id, t) for t in (last_dawn, now, now - timedelta(days=1)))
    if dawn_do is None or today is None or yesterday is None:
        return None
    return dawn_do + (today - yesterday)
