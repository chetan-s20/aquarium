from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import Device, Sensor

from conftest import DEVICE


def _offline_alerts(client):
    return [a for a in client.get("/alerts", params={"limit": 500}).json()
            if a["metric"] == "device_offline" and a["resolved_at"] is None]


def test_device_offline_alert_opens_once_and_resolves_on_reading(client):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(Device(id="silent-a", tank_id="tank-a", name="silent probe", device_type="water_probe",
                      status="gateway", last_seen_at=now - timedelta(hours=2)))
        db.add(Sensor(id="silent-a-dissolved_oxygen", device_id="silent-a", tank_id="tank-a",
                      metric="dissolved_oxygen", unit="mg/L", physical_min=0, physical_max=10))
        db.commit()

    alerts = _offline_alerts(client)
    assert len(alerts) == 1
    assert alerts[0]["device_id"] == "silent-a"
    assert alerts[0]["severity"] == "warning"
    assert _offline_alerts(client)  # the sweep does not open a second alert
    assert len(_offline_alerts(client)) == 1

    r = client.post("/readings", json={"sensor_id": "silent-a-dissolved_oxygen", "value": 6.5,
                                       "observed_at": now.isoformat()}, headers=DEVICE)
    assert r.status_code == 201
    assert not [a for a in _offline_alerts(client) if a["resolved_at"] is None]


def test_active_device_gets_no_alert(client):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(Device(id="loud-a", tank_id="tank-a", name="live probe", device_type="water_probe",
                      status="gateway", last_seen_at=now - timedelta(minutes=2)))
        db.commit()
    assert _offline_alerts(client) == []


def test_simulated_devices_do_not_alert(client):
    # seed devices are status="simulated": they never report by design
    assert _offline_alerts(client) == []
