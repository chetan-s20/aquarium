"""Forecast tonight's pre-dawn dissolved oxygen from the recent trend (Phase 5).

Data-driven: least-squares fit of DO vs local hour over the last readings before dawn,
extrapolated to the next local dawn (farm offset, DAWN_HOUR). Pure trend — no weather
source yet (plan §5).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Reading

DAWN_HOUR = 4.0  # farm-local hour of the pre-dawn DO low


def dawn_do_forecast(db: Session, tank_id: str, now: Optional[datetime] = None) -> Optional[float]:
    """Forecast DO at the next local dawn, or None when there are fewer than 2 readings."""
    now = now or datetime.now(timezone.utc)
    local_now = now + timedelta(hours=settings.farm_utc_offset_hours)
    h = (DAWN_HOUR - local_now.hour) % 24 or 24
    dawn = now + timedelta(hours=h)
    rows = db.query(Reading).filter(
        Reading.tank_id == tank_id,
        Reading.metric == "dissolved_oxygen",
        Reading.quality_status == "valid",
        Reading.value.isnot(None),
        Reading.observed_at < dawn,
    ).order_by(Reading.observed_at.desc()).limit(50).all()
    pts = sorted((r.observed_at, r.value) for r in rows)
    if len(pts) < 2:
        return None

    def x(t: datetime) -> float:
        lt = t + timedelta(hours=settings.farm_utc_offset_hours)
        return lt.hour + lt.minute / 60

    fit = _fit([x(t) for t, _ in pts], [v for _, v in pts])
    if fit is None:
        return None
    a, b = fit
    return a + b * (local_now.hour + h)


def _fit(xs: list[float], ys: list[float]) -> Optional[tuple[float, float]]:
    """Least-squares y = a + b*x; returns (a, b), or None when x has no spread."""
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    denom = n * sum(x * x for x in xs) - sx * sx
    if denom == 0:
        return sum(ys) / n, 0.0
    b = (n * sum(x * y for x, y in zip(xs, ys)) - sx * sy) / denom
    return (sy - b * sx) / n, b
