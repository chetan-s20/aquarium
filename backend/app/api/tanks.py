from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Tank
from app.schemas import TankCreate, TankRead

router = APIRouter(prefix="/tanks", tags=["tanks"])


@router.get("", response_model=list[TankRead])
def list_tanks(db: Session = Depends(get_db)):
    return db.query(Tank).order_by(Tank.created_at).all()


@router.post("", response_model=TankRead, status_code=201)
def create_tank(payload: TankCreate, db: Session = Depends(get_db)):
    tank = Tank(**payload.model_dump())
    db.add(tank)
    db.commit()
    db.refresh(tank)
    return tank


@router.get("/{tank_id}", response_model=TankRead)
def get_tank(tank_id: str, db: Session = Depends(get_db)):
    tank = db.get(Tank, tank_id)
    if not tank:
        raise HTTPException(status_code=404, detail="tank not found")
    return tank
