"""Per-fish behaviour and health from tracked positions.

Positions use a side view of the tank: x 0 = left wall .. 1 = right wall, y 0 = surface .. 1 = bottom.
Health is judged by comparing each fish with its tankmates on the same day, not against fixed
numbers: what is "normal" differs by species, size and camera, but a fish that behaves very
differently from the rest of its group is worth a look (see docs/PLAN.md, Fish tracking).
"""
import math
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Fish, FishPosition, Tank

SURFACE_BAND = 0.15  # top 15% of the water column
BOTTOM_BAND = 0.85  # bottom 15%
ACTIVE_CM_S = 0.3  # slower than this between two samples counts as resting
MAX_GAP_S = 300  # don't draw/measure a path across gaps longer than this (fish hidden)
NOT_SEEN_HOURS = 2
GRID_COLS, GRID_ROWS = 8, 5
MIN_POINTS = 20  # need this many samples before judging a fish
DEFAULT_LENGTH_CM, DEFAULT_DEPTH_CM = 100.0, 50.0


def as_utc(d: datetime) -> datetime:
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def local_day_window(day: Optional[date]) -> tuple[datetime, datetime, date]:
    """A calendar day on the farm clock, as a UTC window."""
    offset = timedelta(hours=settings.farm_utc_offset_hours)
    if day is None:
        day = (datetime.now(timezone.utc) + offset).date()
    start = datetime.combine(day, time.min, tzinfo=timezone.utc) - offset
    return start, start + timedelta(days=1), day


# ---------------------------------------------------------------- ingest

def ingest_positions(db: Session, tank: Tank, items: list[dict]) -> dict:
    """items: {track_key, observed_at, x, y, size?, color_hex?}. New track keys become new fish."""
    fish_by_key = {f.track_key: f for f in db.query(Fish).filter(Fish.tank_id == tank.id)}
    count = len(fish_by_key)
    created = 0
    for it in items:
        if it["track_key"] not in fish_by_key:
            count += 1
            created += 1
            f = Fish(tank_id=tank.id, track_key=it["track_key"], name=f"Fish {count}", color_hex=it.get("color_hex"))
            db.add(f)
            fish_by_key[it["track_key"]] = f
    db.flush()

    times = [as_utc(it["observed_at"]) for it in items]
    existing = set()
    if times:
        existing = {
            (fid, as_utc(t))
            for fid, t in db.query(FishPosition.fish_id, FishPosition.observed_at).filter(
                FishPosition.tank_id == tank.id,
                FishPosition.observed_at >= min(times),
                FishPosition.observed_at <= max(times),
            )
        }
    rows, dup = [], 0
    for it, t in zip(items, times):
        f = fish_by_key[it["track_key"]]
        if (f.id, t) in existing:
            dup += 1
            continue
        existing.add((f.id, t))
        rows.append(dict(fish_id=f.id, tank_id=tank.id, observed_at=t, x=it["x"], y=it["y"], size=it.get("size"),
                         source=it.get("source", "camera")))
        f.first_seen_at = min(as_utc(f.first_seen_at), t) if f.first_seen_at else t
        f.last_seen_at = max(as_utc(f.last_seen_at), t) if f.last_seen_at else t
        if it.get("color_hex") and not f.color_hex:
            f.color_hex = it["color_hex"]
    if rows:
        db.bulk_insert_mappings(FishPosition, rows)
    db.commit()
    return {"stored": len(rows), "duplicates": dup, "new_fish": created}


# ---------------------------------------------------------------- analysis

def _area_words(grid: list[list[float]]) -> str:
    """Which part of the tank the fish uses most, in plain words."""
    rows = [sum(r) for r in grid]
    cols = [sum(grid[r][c] for r in range(GRID_ROWS)) for c in range(GRID_COLS)]
    if not sum(rows):
        return "unknown"
    v = ["near the surface", "in the upper water", "in mid-water", "in the lower water", "near the bottom"][rows.index(max(rows))]
    third = cols.index(max(cols)) * 3 // GRID_COLS
    spread = max(cols) / sum(cols) < 0.25
    return v if spread else f"{v}, {['left side', 'middle', 'right side'][third]}"


def _analyse(points: list[tuple], L: float, D: float, start: datetime, end: datetime) -> dict:
    """points: [(t, x, y, size)] sorted. Returns behaviour numbers for one fish."""
    offset = timedelta(hours=settings.farm_utc_offset_hours)
    grid = [[0.0] * GRID_COLS for _ in range(GRID_ROWS)]
    hourly_dist = [0.0] * 24
    hourly_time = [0.0] * 24
    distance = moving_s = total_s = 0.0
    surface = bottom = 0
    for i, (t, x, y, _) in enumerate(points):
        grid[min(GRID_ROWS - 1, int(y * GRID_ROWS))][min(GRID_COLS - 1, int(x * GRID_COLS))] += 1
        surface += y < SURFACE_BAND
        bottom += y > BOTTOM_BAND
        if i == 0:
            continue
        t0, x0, y0, _ = points[i - 1]
        dt = (t - t0).total_seconds()
        if dt <= 0 or dt > MAX_GAP_S:
            continue
        d = math.hypot((x - x0) * L, (y - y0) * D)
        distance += d
        total_s += dt
        moving_s += dt if d / dt >= ACTIVE_CM_S else 0
        h = (t + offset).hour
        hourly_dist[h] += d
        hourly_time[h] += dt
    n = len(points)
    gaps = sorted((points[i][0] - points[i - 1][0]).total_seconds() for i in range(1, n)) or [0]
    step = gaps[len(gaps) // 2]
    sizes = [s for *_, s in points if s]
    return {
        "samples": n,
        "seen_pct": round(min(1.0, n * step / (end - start).total_seconds()) * 100, 1) if n else 0.0,
        "distance_m": round(distance / 100, 1),
        "active_pct": round(100 * moving_s / total_s, 1) if total_s else 0.0,
        "avg_speed_cm_s": round(distance / total_s, 2) if total_s else 0.0,
        "surface_pct": round(100 * surface / n, 1) if n else 0.0,
        "bottom_pct": round(100 * bottom / n, 1) if n else 0.0,
        "size_cm": round(median(sizes) * L, 1) if sizes else None,
        "hourly_speed_cm_s": [round(hourly_dist[h] / hourly_time[h], 2) if hourly_time[h] else None for h in range(24)],
        "heatmap": [[round(c / n, 4) if n else 0 for c in row] for row in grid],
        "favourite_area": _area_words(grid),
    }


def _neighbour_cm(by_fish: dict[str, list[tuple]], L: float, D: float) -> dict[str, Optional[float]]:
    """Average distance from each fish to its nearest tankmate, at moments both were seen."""
    at: dict[datetime, list[tuple]] = defaultdict(list)
    for fid, pts in by_fish.items():
        for t, x, y, _ in pts:
            at[t].append((fid, x, y))
    sums: dict[str, list[float]] = defaultdict(list)
    for group in at.values():
        if len(group) < 2:
            continue
        for fid, x, y in group:
            sums[fid].append(min(math.hypot((x - x2) * L, (y - y2) * D) for f2, x2, y2 in group if f2 != fid))
    return {fid: (round(sum(v) / len(v), 1) if v else None) for fid, v in ((f, sums.get(f, [])) for f in by_fish)}


def _health(s: dict, group: dict, last_seen: Optional[datetime], is_today: bool, now: datetime) -> tuple[str, list[dict]]:
    """Plain-language flags from comparing one fish with the tank's typical fish."""
    flags: list[dict] = []
    if is_today and last_seen and now - last_seen > timedelta(hours=NOT_SEEN_HOURS):
        hours = int((now - last_seen).total_seconds() // 3600)
        flags.append({"level": "check", "text": f"Not seen by the camera for {hours} hours",
                      "advice": "Look for it in the tank: it may be hiding, stuck, or dead."})
    if s["samples"] >= MIN_POINTS and group:
        act = group.get("active_pct")
        if act and s["active_pct"] < 0.3 * act:
            flags.append({"level": "check", "text": "Much less active than the other fish",
                          "advice": "Check it closely for spots, torn fins, swelling or a swollen belly. Consider moving it to a separate tank."})
        elif act and s["active_pct"] < 0.55 * act:
            flags.append({"level": "watch", "text": "Less active than the other fish",
                          "advice": "Watch it at feeding time: a fish that ignores food is often unwell."})
        if s["bottom_pct"] > max(40.0, 2 * group.get("bottom_pct", 0)):
            flags.append({"level": "watch", "text": "Resting on the bottom much of the time",
                          "advice": "Sitting on the bottom can mean weakness or illness."})
        if s["surface_pct"] > max(25.0, 2 * group.get("surface_pct", 0)):
            flags.append({"level": "watch", "text": "Often staying at the surface",
                          "advice": "Fish gulp air at the surface when oxygen is low or gills are damaged. Check the oxygen reading and aerator."})
        nb = group.get("neighbour_cm")
        if nb and s.get("neighbour_cm") and s["neighbour_cm"] > 1.8 * nb:
            flags.append({"level": "watch", "text": "Keeping away from the other fish",
                          "advice": "Sick fish often separate from the group. It may also be getting chased."})
    levels = [f["level"] for f in flags]
    status = "check" if "check" in levels or len(levels) >= 2 else ("watch" if levels else "healthy")
    if s["samples"] < MIN_POINTS and not flags:
        status = "unknown"
    return status, flags


def _sentence(f: Fish, s: dict, group: dict, rank: Optional[int], n: int) -> str:
    if s["samples"] < MIN_POINTS:
        return f"{f.name} was hardly seen by the camera on this day, so there is not enough to judge."
    parts = [f"{f.name} swam about {s['distance_m']:.0f} m and was moving {s['active_pct']:.0f}% of the time."]
    if rank is not None and n > 2:
        if rank <= max(1, n // 4):
            parts.append("That makes it one of the most active fish in the tank.")
        elif rank > n - max(1, n // 4):
            parts.append("That makes it one of the least active fish in the tank.")
        else:
            parts.append("That is about normal for this tank.")
    parts.append(f"It spends most of its time {s['favourite_area']}.")
    return " ".join(parts)


def tank_fish_report(db: Session, tank: Tank, day: Optional[date] = None, detail_fish_id: Optional[str] = None) -> dict:
    """Behaviour + health for every fish in the tank on one farm-local day."""
    start, end, day = local_day_window(day)
    now = datetime.now(timezone.utc)
    L, D = tank.length_cm or DEFAULT_LENGTH_CM, tank.depth_cm or DEFAULT_DEPTH_CM
    fish = db.query(Fish).filter(Fish.tank_id == tank.id).order_by(Fish.created_at, Fish.name).all()
    by_fish: dict[str, list[tuple]] = {f.id: [] for f in fish}
    q = (
        db.query(FishPosition.fish_id, FishPosition.observed_at, FishPosition.x, FishPosition.y, FishPosition.size)
        .filter(FishPosition.tank_id == tank.id, FishPosition.observed_at >= start, FishPosition.observed_at < end)
        .order_by(FishPosition.observed_at)
    )
    for fid, t, x, y, size in q:
        if fid in by_fish:
            by_fish[fid].append((as_utc(t), x, y, size))

    stats = {f.id: _analyse(by_fish[f.id], L, D, start, end) for f in fish}
    for fid, nb in _neighbour_cm(by_fish, L, D).items():
        stats[fid]["neighbour_cm"] = nb
    judged = [stats[f.id] for f in fish if f.status == "in_tank" and stats[f.id]["samples"] >= MIN_POINTS]
    group = {
        k: round(median([s[k] for s in judged if s.get(k) is not None]), 2)
        for k in ("active_pct", "distance_m", "surface_pct", "bottom_pct", "neighbour_cm", "avg_speed_cm_s")
        if any(s.get(k) is not None for s in judged)
    } if judged else {}
    order = sorted((f.id for f in fish if stats[f.id]["samples"] >= MIN_POINTS), key=lambda i: -stats[i]["active_pct"])
    is_today = start <= now < end

    out = []
    for f in fish:
        s = stats[f.id]
        last_seen = as_utc(f.last_seen_at) if f.last_seen_at else None
        status, flags = ("removed", []) if f.status == "removed" else _health(s, group, last_seen, is_today, now)
        rank = order.index(f.id) + 1 if f.id in order else None
        pts = by_fish[f.id]
        last = pts[-1] if pts else None
        heading = 0
        if len(pts) >= 2:
            heading = 1 if pts[-1][1] >= pts[-2][1] else -1
        row = {
            "id": f.id, "name": f.name, "track_key": f.track_key, "color_hex": f.color_hex, "notes": f.notes,
            "in_tank": f.status == "in_tank", "status": status, "flags": flags,
            "first_seen_at": f.first_seen_at and as_utc(f.first_seen_at), "last_seen_at": last_seen,
            "last_position": {"x": last[1], "y": last[2], "heading": heading} if last else None,
            "activity_rank": rank, "summary": _sentence(f, s, group, rank, len(order)),
            **{k: v for k, v in s.items() if k not in ("heatmap", "hourly_speed_cm_s")},
        }
        if f.id == detail_fish_id:
            step = max(1, len(pts) // 720)
            row["heatmap"] = s["heatmap"]
            row["hourly_speed_cm_s"] = s["hourly_speed_cm_s"]
            row["path"] = [{"t": t, "x": round(x, 4), "y": round(y, 4)} for t, x, y, _ in pts[::step]]
        out.append(row)

    rank_status = {"check": 0, "watch": 1, "unknown": 2, "healthy": 3, "removed": 4}
    natural = lambda name: [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]  # noqa: E731
    out.sort(key=lambda r: (rank_status[r["status"]], natural(r["name"])))
    return {
        "tank_id": tank.id, "day": day.isoformat(), "window_start": start, "window_end": end,
        "tank_length_cm": L, "tank_depth_cm": D, "group": group, "fish": out,
    }
