import csv
import io
from datetime import datetime, timedelta, timezone

from app.config import settings
from conftest import DEVICE, login


BASE = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=30)  # before any simulated data


def _post(client, sensor_id, value, minutes_ago, **extra):
    at = (BASE - timedelta(minutes=minutes_ago)).isoformat()
    return client.post("/readings", json={"sensor_id": sensor_id, "value": value, "observed_at": at, **extra}, headers=DEVICE)


def test_sensors_have_no_tds_and_include_dissolved_oxygen(client):
    metrics = {s["metric"] for s in client.get("/tanks/tank-a/sensors").json()}
    assert "tds" not in metrics
    assert {"dissolved_oxygen", "temperature", "ph", "turbidity", "fish_activity"} <= metrics


def test_write_endpoints_need_keys(client):
    client.cookies.clear()
    assert client.post("/simulate/run", params={"tank_id": "tank-a"}).status_code == 401
    assert client.post("/readings", json={"sensor_id": "x", "observed_at": "2026-01-01T00:00:00Z"}).status_code == 401
    assert client.post("/tanks", json={"name": "x"}).status_code == 401


def test_reading_takes_tank_metric_unit_from_sensor_and_rejects_duplicates(client):
    r = _post(client, "tank-b-ph", 7.4, 500)
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["tank_id"], body["metric"], body["unit"], body["quality_status"]) == ("tank-b", "ph", "pH", "valid")
    assert body["observed_at"].endswith(("Z", "+00:00"))
    assert _post(client, "tank-b-ph", 7.4, 500).status_code == 409
    assert _post(client, "tank-b-ph", 99, 499).json()["quality_status"] == "invalid"
    assert _post(client, "no-such-sensor", 1, 1).status_code == 404


def test_alert_opens_escalates_and_resolves(client):
    sid = "tank-b-dissolved_oxygen"

    def active():
        alerts = client.get("/alerts", params={"tank_id": "tank-b", "limit": 500}).json()
        return [a for a in alerts if a["sensor_id"] == sid and a["resolved_at"] is None]

    # resolve whatever the 24h simulation left open, so we start clean
    _post(client, sid, 8.0, 400)
    assert active() == []

    _post(client, sid, 4.5, 300)  # below 5.0 warning
    [a] = active()
    assert a["severity"] == "warning"
    _post(client, sid, 2.5, 290)  # below 3.0 critical -> same alert escalates
    [a] = active()
    assert a["severity"] == "critical"
    _post(client, sid, 5.1, 280)  # inside hysteresis (5.0 + 0.3): still active
    assert len(active()) == 1
    _post(client, sid, 6.0, 270)  # recovered
    assert active() == []

    login(client)
    ack = client.post(f"/alerts/{a['id']}/acknowledge").json()
    assert ack["status"] == "resolved" and ack["acknowledged_by"] == "operator"

    _post(client, sid, 4.0, 260)  # a new dip after recovery opens a NEW alert
    [b] = active()
    assert b["id"] != a["id"]
    _post(client, sid, 7.0, 250)


def test_simulated_week_raises_an_alert_per_dawn_dip(client):
    # the seed covers 24h, so at least one dawn DO dip below 5 mg/L per tank
    alerts = client.get("/alerts", params={"tank_id": "tank-a"}).json()
    assert any(a["metric"] == "dissolved_oxygen" for a in alerts)


def test_simulation_tops_up_without_duplicates(client):
    login(client)
    first = client.post("/simulate/run", params={"tank_id": "tank-a"}).json()["inserted"]
    assert first < 6 * 3  # already filled to ~now by the seed
    readings = client.get("/readings", params={"tank_id": "tank-a", "metric": "temperature", "limit": 20000}).json()
    times = [r["observed_at"] for r in readings]
    assert len(times) == len(set(times))
    assert times == sorted(times)


def test_simulated_dissolved_oxygen_follows_daily_cycle(client):
    readings = client.get("/readings", params={"tank_id": "tank-a", "metric": "dissolved_oxygen", "limit": 500}).json()
    by_hour = {}
    for r in readings:
        if r["quality_status"] == "valid":
            local = datetime.fromisoformat(r["observed_at"]) + timedelta(hours=settings.farm_utc_offset_hours)
            by_hour.setdefault(local.hour, []).append(r["value"])
    # farm-local afternoon high, pre-dawn low
    assert sum(by_hour[16]) / len(by_hour[16]) > sum(by_hour[4]) / len(by_hour[4]) + 2


def test_readings_window_filter(client):
    start = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    readings = client.get("/readings", params={"tank_id": "tank-a", "start": start}).json()
    assert readings and all(r["observed_at"] >= start[:16] for r in readings)


def test_export_long_and_wide(client):
    long = client.get("/export/readings.csv", params={"tank_id": "tank-a", "metric": ["ph", "dissolved_oxygen"]})
    assert long.status_code == 200 and long.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(long.text)))
    assert rows and {r["metric"] for r in rows} == {"ph", "dissolved_oxygen"}
    assert rows[0]["observed_at"].endswith("Z") and rows[0]["tank_name"] == "Tank A"

    wide = client.get("/export/readings.csv", params={"tank_id": "tank-a", "layout": "wide", "valid_only": True})
    header = next(csv.reader(io.StringIO(wide.text)))
    assert header[:3] == ["observed_at", "tank_id", "tank_name"]
    assert {"dissolved_oxygen", "fish_activity", "surface_activity"} <= set(header)


def test_import_preview_and_commit(client):
    data = (
        "Probe;Value;Time\n"
        "tank-b-temperature;28.5;2025-01-01T06:00:00Z\n"
        "tank-b-temperature;28.6;2025-01-01T06:00:00Z\n"
        "tank-b-temperature;abc;2025-01-01T06:10:00Z\n"
        "unknown-sensor;1;2025-01-01T06:20:00Z\n"
    ).encode()
    mapping = '{"sensor_id": "Probe", "value": "Value", "observed_at": "Time"}'
    files = {"file": ("t.csv", io.BytesIO(data), "text/csv")}
    p = client.post("/imports/preview", files=files, data={"mapping": mapping}).json()
    assert (p["row_count"], p["accepted_count"], p["duplicate_count"]) == (4, 2, 1)

    files = {"file": ("t.csv", io.BytesIO(data), "text/csv")}
    login(client)
    c = client.post("/imports/commit", files=files, data={"mapping": mapping}).json()
    assert (c["accepted_count"], c["rejected_count"]) == (1, 3)


def test_thresholds_are_effective_per_metric(client):
    rows = client.get("/tanks/tank-a/thresholds").json()
    by_metric = {t["metric"]: t for t in rows}
    assert by_metric["dissolved_oxygen"]["low_warning"] == 5.0
    assert "tds" not in by_metric and "fish_activity" not in by_metric
