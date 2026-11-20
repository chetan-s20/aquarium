from app.config import settings
from conftest import login


def test_login_and_me(client):
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401
    r = client.post("/auth/login", json={"name": "operator", "password": settings.operator_password})
    assert r.status_code == 200
    assert r.json()["name"] == "operator" and r.json()["role"] == "operator"
    assert client.get("/auth/me").json()["name"] == "operator"
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_login_rejects_bad_credentials(client):
    client.cookies.clear()
    assert client.post("/auth/login", json={"name": "operator", "password": "wrong-password"}).status_code == 401
    assert client.post("/auth/login", json={"name": "nobody", "password": "x"}).status_code == 401


def test_operator_endpoints_require_a_session(client):
    client.cookies.clear()
    assert client.post("/tanks", json={"name": "Auth Test Tank"}).status_code == 401
    login(client)
    assert client.post("/tanks", json={"name": "Auth Test Tank"}).status_code == 201
