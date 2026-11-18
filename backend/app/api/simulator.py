from fastapi import APIRouter, Depends, HTTPException, Security

from app.security import require_operator_key
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Tank
from app.services.simulator import run_simulation

router = APIRouter(prefix="/simulate", tags=["simulator"])


@router.post("/run")
def simulate(tank_id: str, count: int = 24, interval_minutes: int = 5, db: Session = Depends(get_db), _key: str = Security(require_operator_key)):
    tank = db.get(Tank, tank_id)
    if not tank:
        raise HTTPException(status_code=404, detail="tank not found")
    inserted = run_simulation(db, tank_id, count=count, interval_minutes=interval_minutes)
    return {"tank_id": tank_id, "inserted": inserted, "source": "simulator"}
