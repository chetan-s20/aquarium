from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.db import get_db
from app.models import Tank, User
from app.services.fish_simulator import simulate_fish
from app.services.simulator import run_simulation

router = APIRouter(prefix="/simulate", tags=["simulator"])


@router.post("/run")
def simulate(
    tank_id: str,
    hours: int = Query(24, ge=1, le=24 * 30),
    interval_minutes: int = Query(10, ge=1, le=60),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Fill SIMULATED readings from the tank's last reading up to now."""
    if not settings.simulation_mode:
        raise HTTPException(status_code=403, detail="simulation is disabled (SIMULATION_MODE=false)")
    if not db.get(Tank, tank_id):
        raise HTTPException(status_code=404, detail="tank not found")
    inserted = run_simulation(db, tank_id, hours=hours, interval_minutes=interval_minutes)
    positions = simulate_fish(db, tank_id, hours=min(hours, 48))
    return {"tank_id": tank_id, "inserted": inserted, "fish_positions": positions, "source": "simulator"}
