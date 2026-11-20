"""Data-driven low limits for camera activity metrics (Phase 4).

Hypoxia stalls fish, so activity during low-DO windows is usually well below normal.
We pair activity readings with nearby dissolved-oxygen readings and return a proposed
low limit for the activity metric: `low_warning` = the activity level typically reached
during low-DO events. The proposal needs at least `min_events` low-DO events with
activity — "5 real low-DO events" in plan §4. Review before enabling it on the farm.
"""
from statistics import median
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Reading
from app.services.alerts import thresholds_for

ACTIVITY_PAIR_MINUTES = 30


def derive_activity_limits(db: Session, tank_id: str, metric: str = "fish_activity",
                           min_events: int = 5) -> Optional[dict]:
    do_pts = _valid_points(db, tank_id, "dissolved_oxygen")
    act_pts = _valid_points(db, tank_id, metric)
    if len(do_pts) < 3 or len(act_pts) < 3:
        return None
    t = thresholds_for(db, tank_id, "dissolved_oxygen")
    floor = t.low_warning if (t and t.low_warning is not None) else median([v for _, v in do_pts])
    if floor is None:
        return None
    during = []
    events = 0
    for ts, v in do_pts:
        if v >= floor:
            continue
        events += 1
        during.extend(a for ats, a in act_pts
                      if a is not None and 0 <= (ats - ts).total_seconds() <= ACTIVITY_PAIR_MINUTES * 60)
    if events < min_events or len(during) < min_events:
        return None
    during.sort()
    return {
        "tank_id": tank_id,
        "metric": metric,
        "do_floor": floor,
        "low_events": events,
        "low_warning": during[len(during) // 10],
    }


def _valid_points(db: Session, tank_id: str, metric: str) -> list[tuple[object, float]]:
    rows = db.query(Reading).filter(
        Reading.tank_id == tank_id,
        Reading.metric == metric,
        Reading.quality_status == "valid",
        Reading.value.isnot(None),
    ).order_by(Reading.observed_at).all()
    return [(r.observed_at, r.value) for r in rows]
