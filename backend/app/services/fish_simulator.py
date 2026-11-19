"""SIMULATED fish positions for the demo (source="simulator"). Replace with ml/track_fish.py output.

Each fish has its own personality (how active, how social, preferred depth). The school
drifts around the tank, is calmer and lower at night, and rises toward the surface around
dawn when oxygen is lowest. Three fish per tank are built to show the health flags:
  #3 sick: sluggish, stays on the bottom, away from the group
  #7 short of air: hangs at the surface
  #10 missing: not seen for the last few hours
"""
import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Fish, FishPosition, Tank
from app.services.fish import ingest_positions

FISH_PER_TANK = 12
BODY_COLOURS = ["#d9822b", "#c9ccd1", "#8c916f", "#e3b448", "#a8623b", "#9fb6c4",
                "#6f7d8c", "#e8d9b5", "#b5483a", "#7a6a55", "#c7a26b", "#5f8a8b"]
SICK, SURFACE, MISSING = "3", "7", "10"


def _persona(key: str, rng: random.Random) -> dict:
    p = {"activity": rng.uniform(0.8, 1.25), "social": rng.uniform(0.5, 1.0), "depth": rng.uniform(0.35, 0.7),
         "length_cm": rng.uniform(7, 13)}
    if key == SICK:
        p.update(activity=0.22, social=0.0, depth=0.93)
    if key == SURFACE:
        p.update(depth=0.06, activity=0.9)
    return p


def simulate_fish(db: Session, tank_id: str, hours: int = 24, interval_s: int = 30, seed: int | None = None) -> int:
    tank = db.get(Tank, tank_id)
    if tank is None:
        return 0
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now -= timedelta(seconds=now.second % interval_s)
    last = db.query(func.max(FishPosition.observed_at)).filter(FishPosition.tank_id == tank_id).scalar()
    start = now - timedelta(hours=hours)
    if last is not None:
        last = last.replace(tzinfo=timezone.utc) if last.tzinfo is None else last
        start = max(start, last + timedelta(seconds=interval_s))
    if start > now:
        return 0

    # personalities are fixed per tank + fish so top-ups continue the same story
    keys = [str(i) for i in range(1, FISH_PER_TANK + 1)]
    personas = {k: _persona(k, random.Random(f"{tank_id}-{k}")) for k in keys}
    rng = random.Random(seed)
    L = tank.length_cm or 100.0
    offset = timedelta(hours=settings.farm_utc_offset_hours)
    pos = {k: [rng.uniform(0.2, 0.8), personas[k]["depth"]] for k in keys}
    school = [0.5, 0.5]
    items = []
    t = start
    while t <= now:
        hour = (t + offset).hour + (t + offset).minute / 60
        night = hour < 6 or hour >= 21
        dawn_rise = max(0.0, 1 - abs(hour - 5.5) / 1.5)  # 0..1 around 04:00-07:00
        school[0] = min(0.8, max(0.2, school[0] + rng.gauss(0, 0.03)))
        school[1] = min(0.7, max(0.3, school[1] + rng.gauss(0, 0.02)))
        for k in keys:
            if k == MISSING and t > now - timedelta(hours=3):
                continue
            p, s = personas[k], pos[k]
            act = p["activity"] * (0.35 if night else 1.0)
            depth = p["depth"] if k in (SICK, SURFACE) else (0.6 if night else p["depth"]) - 0.35 * dawn_rise
            s[0] += p["social"] * 0.15 * (school[0] - s[0]) + rng.gauss(0, 0.12 * act)
            s[1] += 0.12 * (depth - s[1]) + p["social"] * 0.05 * (school[1] - s[1]) + rng.gauss(0, 0.06 * act)
            for i in (0, 1):  # bounce off the glass / surface / bottom
                s[i] = 0.02 + abs(s[i] - 0.02) if s[i] < 0.02 else s[i]
                s[i] = 0.98 - abs(s[i] - 0.98) if s[i] > 0.98 else s[i]
            items.append({
                "track_key": k, "observed_at": t, "x": round(s[0], 4), "y": round(s[1], 4),
                "size": round(p["length_cm"] * (1 + rng.gauss(0, 0.04)) / L, 4),
                "color_hex": BODY_COLOURS[(int(k) - 1) % len(BODY_COLOURS)], "source": "simulator",
            })
        t += timedelta(seconds=interval_s)
    if not items:
        return 0
    return ingest_positions(db, tank, items)["stored"]
