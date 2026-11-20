from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import Sensor, Tank, Threshold, User
from app.schemas import SensorRead, TankCreate, TankRead, ThresholdRead
from app.services.audit import audit

router = APIRouter(prefix="/tanks", tags=["tanks"])


def _tank(db: Session, tank_id: str) -> Tank:
    tank = db.get(Tank, tank_id)
    if not tank:
        raise HTTPException(status_code=404, detail="tank not found")
    return tank


@router.get("", response_model=list[TankRead])
def list_tanks(db: Session = Depends(get_db)):
    return db.query(Tank).order_by(Tank.created_at).all()


@router.post("", response_model=TankRead, status_code=201)
def create_tank(payload: TankCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    tank = Tank(**payload.model_dump())
    db.add(tank)
    db.flush()
    audit(db, user.name, "create_tank", "tank", tank.id, payload.name)
    db.commit()
    db.refresh(tank)
    return tank


@router.get("/{tank_id}", response_model=TankRead)
def get_tank(tank_id: str, db: Session = Depends(get_db)):
    return _tank(db, tank_id)


@router.get("/{tank_id}/sensors", response_model=list[SensorRead])
def list_sensors(tank_id: str, db: Session = Depends(get_db)):
    _tank(db, tank_id)
    return db.query(Sensor).filter(Sensor.tank_id == tank_id).order_by(Sensor.metric).all()


@router.get("/{tank_id}/thresholds", response_model=list[ThresholdRead])
def list_thresholds(tank_id: str, db: Session = Depends(get_db)):
    """Effective limits per metric: tank-specific rows override global (tank_id NULL) ones."""
    _tank(db, tank_id)
    rows = db.query(Threshold).filter((Threshold.tank_id == tank_id) | (Threshold.tank_id.is_(None))).all()
    effective: dict[str, Threshold] = {}
    for t in sorted(rows, key=lambda t: t.tank_id is not None):
        effective[t.metric] = t
    return list(effective.values())
