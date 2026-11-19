"""CSV export for analysts: water quality and camera behaviour metrics in one file."""
import csv
import io
from datetime import timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Fish, FishPosition, Reading, Tank
from app.schemas import UTCDateTime

router = APIRouter(prefix="/export", tags=["export"])


def _iso(d) -> str:
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat().replace("+00:00", "Z")


@router.get("/readings.csv")
def export_readings(
    tank_id: list[str] | None = Query(None),
    metric: list[str] | None = Query(None),
    start: UTCDateTime | None = None,
    end: UTCDateTime | None = None,
    layout: Literal["long", "wide"] = "long",
    valid_only: bool = False,
    db: Session = Depends(get_db),
):
    """long = one row per reading (with quality + source).
    wide = one row per tank and timestamp, one column per metric (ready for pandas / Excel)."""
    q = db.query(Reading, Tank.name).join(Tank, Tank.id == Reading.tank_id)
    if tank_id:
        q = q.filter(Reading.tank_id.in_(tank_id))
    if metric:
        q = q.filter(Reading.metric.in_(metric))
    if start:
        q = q.filter(Reading.observed_at >= start)
    if end:
        q = q.filter(Reading.observed_at <= end)
    if valid_only:
        q = q.filter(Reading.quality_status == "valid")
    # shortcut: builds the file in memory; fine to ~1M rows, stream it if exports grow past that
    rows = q.order_by(Reading.tank_id, Reading.observed_at, Reading.metric).all()

    buf = io.StringIO()
    w = csv.writer(buf)
    if layout == "long":
        w.writerow(["observed_at", "tank_id", "tank_name", "sensor_id", "metric", "value", "unit", "quality_status", "source"])
        for r, name in rows:
            w.writerow([_iso(r.observed_at), r.tank_id, name, r.sensor_id, r.metric, r.value, r.unit, r.quality_status, r.source])
    else:
        metrics = sorted({r.metric for r, _ in rows})
        table: dict[tuple, dict] = {}
        for r, name in rows:
            table.setdefault((r.tank_id, name, r.observed_at), {})[r.metric] = r.value
        w.writerow(["observed_at", "tank_id", "tank_name", *metrics])
        for (tid, name, at), values in table.items():
            w.writerow([_iso(at), tid, name, *(values.get(m) for m in metrics)])

    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="aquarium-readings-{layout}.csv"'},
    )


@router.get("/fish-positions.csv")
def export_fish_positions(
    tank_id: list[str] | None = Query(None),
    fish_id: list[str] | None = Query(None),
    start: UTCDateTime | None = None,
    end: UTCDateTime | None = None,
    db: Session = Depends(get_db),
):
    """Every tracked position of every fish: the raw material for behaviour analysis.
    x: 0 = left wall .. 1 = right wall; y: 0 = surface .. 1 = bottom; *_cm use the tank's size."""
    q = (
        db.query(FishPosition, Fish.name, Tank.name, Tank.length_cm, Tank.depth_cm)
        .join(Fish, Fish.id == FishPosition.fish_id)
        .join(Tank, Tank.id == FishPosition.tank_id)
    )
    if tank_id:
        q = q.filter(FishPosition.tank_id.in_(tank_id))
    if fish_id:
        q = q.filter(FishPosition.fish_id.in_(fish_id))
    if start:
        q = q.filter(FishPosition.observed_at >= start)
    if end:
        q = q.filter(FishPosition.observed_at <= end)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["observed_at", "tank_id", "tank_name", "fish_id", "fish_name", "x", "y", "x_cm", "depth_cm", "length_cm", "source"])
    # shortcut: in-memory like readings.csv; ~35k rows per tank-day at 30 s sampling
    for p, fish_name, tank_name, L, D in q.order_by(FishPosition.tank_id, FishPosition.fish_id, FishPosition.observed_at):
        w.writerow([
            _iso(p.observed_at), p.tank_id, tank_name, p.fish_id, fish_name, p.x, p.y,
            round(p.x * L, 1) if L else None, round(p.y * D, 1) if D else None,
            round(p.size * L, 1) if (p.size and L) else None, p.source,
        ])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="fish-positions.csv"'})
