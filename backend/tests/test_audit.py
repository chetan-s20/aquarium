from app.db import SessionLocal
from app.models import AuditLog


def test_audit_log_captures_operator_actions(client):
    from conftest import login
    login(client)
    r = client.post("/tanks", json={"name": "Audit Tank"})
    assert r.status_code == 201
    with SessionLocal() as db:
        rows = [a for a in db.query(AuditLog).filter_by(action="create_tank")
                if a.entity_id == r.json()["id"]]
    assert rows and rows[0].actor == "operator"
