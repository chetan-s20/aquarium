import csv
import io
from datetime import datetime, timedelta, timezone

from app.config import settings
from conftest import DEVICE, login


def _yesterday():
    return (datetime.now(timezone.utc) + timedelta(hours=settings.farm_utc_offset_hours) - timedelta(days=1)).date().isoformat()


def _by_name(report):
    return {f["name"]: f for f in report["fish"]}


def test_tank_lists_every_fish_with_behaviour(client):
    report = client.get("/tanks/tank-a/fish", params={"day": _yesterday()}).json()
    fish = _by_name(report)
    assert len(fish) == 12
    healthy = fish["Fish 1"]
    assert healthy["samples"] > 2000  # a full day at 30 s
    assert healthy["distance_m"] > 0 and 0 < healthy["active_pct"] <= 100
    assert healthy["summary"].startswith("Fish 1 swam about")


def test_unwell_fish_are_flagged_in_plain_words(client):
    fish = _by_name(client.get("/tanks/tank-a/fish", params={"day": _yesterday()}).json())
    sick = fish["Fish 3"]
    assert sick["status"] == "check"
    texts = " ".join(f["text"] for f in sick["flags"])
    assert "less active" in texts and "bottom" in texts
    assert any("surface" in f["text"] for f in fish["Fish 7"]["flags"])
    normal = [f for f in fish.values() if f["name"] not in ("Fish 3", "Fish 7", "Fish 10")]
    assert sum(f["status"] == "healthy" for f in normal) >= len(normal) - 2
    # list is sorted most-urgent first
    assert list(fish.values())[0]["status"] == "check"


def test_missing_fish_flagged_today(client):
    fish = _by_name(client.get("/tanks/tank-a/fish").json())
    assert any(f["text"].startswith("Not seen") for f in fish["Fish 10"]["flags"])


def test_fish_detail_has_path_heatmap_and_hours(client):
    fid = _by_name(client.get("/tanks/tank-a/fish").json())["Fish 1"]["id"]
    d = client.get(f"/fish/{fid}", params={"day": _yesterday()}).json()
    f = d["fish"]
    assert 100 < len(f["path"]) <= 1440
    assert len(f["heatmap"]) == 5 and len(f["heatmap"][0]) == 8
    assert abs(sum(map(sum, f["heatmap"])) - 1) < 0.01
    assert len(f["hourly_speed_cm_s"]) == 24
    assert d["tank_size"] == 12 and d["tank_length_cm"] == 150
    assert client.get("/fish/nope").status_code == 404


def test_tracker_can_post_positions_and_new_fish_appear(client):
    at = "2026-01-01T10:00:00Z"
    batch = {"positions": [{"track_key": "cam-99", "observed_at": at, "x": 0.5, "y": 0.4, "size": 0.07, "color_hex": "#aabbcc"}]}
    assert client.post("/tanks/tank-b/fish-positions", json=batch).status_code == 401
    r = client.post("/tanks/tank-b/fish-positions", json=batch, headers=DEVICE).json()
    assert r == {"stored": 1, "duplicates": 0, "new_fish": 1}
    assert client.post("/tanks/tank-b/fish-positions", json=batch, headers=DEVICE).json()["duplicates"] == 1
    bad = {"positions": [{"track_key": "x", "observed_at": at, "x": 1.5, "y": 0.4}]}
    assert client.post("/tanks/tank-b/fish-positions", json=bad, headers=DEVICE).status_code == 422


def test_staff_can_rename_and_remove_a_fish(client):
    fid = _by_name(client.get("/tanks/tank-b/fish").json())["Fish 2"]["id"]
    client.cookies.clear()
    assert client.patch(f"/fish/{fid}", json={"name": "Goldie"}).status_code == 401
    login(client)
    client.patch(f"/fish/{fid}", json={"name": "Goldie", "notes": "white spot on tail"})
    client.patch(f"/fish/{fid}", json={"status": "removed"})
    f = _by_name(client.get("/tanks/tank-b/fish").json())["Goldie"]
    assert f["status"] == "removed" and f["notes"] == "white spot on tail"


def test_fish_positions_export(client):
    r = client.get("/export/fish-positions.csv", params={"tank_id": "tank-a"})
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) > 10000
    assert {"fish_name", "x_cm", "depth_cm", "length_cm"} <= set(rows[0])
    assert rows[0]["tank_name"] == "Tank A" and rows[0]["observed_at"].endswith("Z")
