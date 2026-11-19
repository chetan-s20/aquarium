from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Security
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Fish, Tank
from app.schemas import UTCDateTime
from app.security import require_device_key, require_operator_key
from app.services.fish import ingest_positions, tank_fish_report

router = APIRouter(tags=["fish"])


class PositionIn(BaseModel):
    track_key: str = Field(min_length=1, max_length=60)
    observed_at: UTCDateTime
    x: float = Field(ge=0, le=1, description="0 = left wall, 1 = right wall")
    y: float = Field(ge=0, le=1, description="0 = water surface, 1 = bottom")
    size: Optional[float] = Field(default=None, gt=0, le=1, description="body length / tank length")
    color_hex: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class PositionBatch(BaseModel):
    positions: list[PositionIn] = Field(max_length=50000)


class FishUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    notes: Optional[str] = Field(default=None, max_length=4000)
    status: Optional[Literal["in_tank", "removed"]] = None


def _tank(db: Session, tank_id: str) -> Tank:
    tank = db.get(Tank, tank_id)
    if not tank:
        raise HTTPException(status_code=404, detail="tank not found")
    return tank


@router.post("/tanks/{tank_id}/fish-positions", status_code=201)
def post_positions(tank_id: str, batch: PositionBatch, db: Session = Depends(get_db), _k: str = Security(require_device_key)):
    """Tracker output. Any tracker works (ours, TRex, idtracker.ai) once mapped to this shape."""
    return ingest_positions(db, _tank(db, tank_id), [p.model_dump() for p in batch.positions])


@router.get("/tanks/{tank_id}/fish")
def list_fish(tank_id: str, day: Optional[date] = None, db: Session = Depends(get_db)):
    """Every fish in the tank with its behaviour and health for one farm-local day (default today)."""
    return tank_fish_report(db, _tank(db, tank_id), day)


@router.get("/fish/{fish_id}")
def get_fish(fish_id: str, day: Optional[date] = None, db: Session = Depends(get_db)):
    """One fish in full: path through the day, where it spends time, activity by hour, health."""
    fish = db.get(Fish, fish_id)
    if not fish:
        raise HTTPException(status_code=404, detail="fish not found")
    report = tank_fish_report(db, _tank(db, fish.tank_id), day, detail_fish_id=fish_id)
    row = next(r for r in report["fish"] if r["id"] == fish_id)
    return {**{k: v for k, v in report.items() if k != "fish"}, "fish": row, "tank_size": len(report["fish"])}


@router.patch("/fish/{fish_id}")
def update_fish(fish_id: str, body: FishUpdate, db: Session = Depends(get_db), _k: str = Security(require_operator_key)):
    fish = db.get(Fish, fish_id)
    if not fish:
        raise HTTPException(status_code=404, detail="fish not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(fish, k, v)
    db.commit()
    return {"id": fish.id, "name": fish.name, "notes": fish.notes, "status": fish.status}
