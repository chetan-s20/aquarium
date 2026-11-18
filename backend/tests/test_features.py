import io

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_auth_required():
    r = client.post("/simulate/run", params={"tank_id": "tank-demo-1"})
    assert r.status_code == 401


def test_create_reading_and_alert():
    payload = {
        "tank_id": "tank-demo-1",
        "sensor_id": "sensor-temp-1",
        "metric": "temperature",
        "value": 35.0,
        "unit": "degC",
        "observed_at": "2026-11-18T12:00:00Z",
        "source": "sensor",
    }
    r = client.post("/readings", json=payload, headers={"X-Device-Key": "dev-device-key-change-me"})
    assert r.status_code == 201
    alerts = client.get("/alerts").json()
    assert any(a["metric"] == "temperature" for a in alerts)


def test_import_preview():
    csv = b"tank_id,sensor_id,metric,value,unit,observed_at\ntank-demo-1,sensor-temp-1,temperature,21.0,degC,2026-11-18T13:00:00Z\n"
    files = {"file": ("t.csv", io.BytesIO(csv), "text/csv")}
    r = client.post("/imports/preview", files=files)
    assert r.status_code == 200
    assert r.json()["accepted_count"] == 1
