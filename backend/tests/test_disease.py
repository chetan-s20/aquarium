from app.api import disease
from app.config import settings
from conftest import login

PHOTO = {"photo": ("fish.jpg", b"\xff\xd8 jpeg bytes", "image/jpeg")}


def test_photo_check_needs_login(client):
    client.cookies.clear()
    assert client.post("/disease/check", files=PHOTO).status_code == 401


def test_photo_check_off_until_configured(client, monkeypatch):
    login(client)
    monkeypatch.setattr(settings, "disease_url", "")
    assert client.post("/disease/check", files=PHOTO).status_code == 503


def test_photo_check_validates_upload_and_passes_model_answer(client, monkeypatch):
    login(client)
    monkeypatch.setattr(settings, "disease_url", "http://checker:8100")
    answer = {"predictions": [{"label": "Healthy Fish", "probability": 0.9}], "model": "test"}
    monkeypatch.setattr(disease, "ask_model", lambda photo: answer)
    assert client.post("/disease/check", files=PHOTO).json() == answer
    assert client.post("/disease/check", files={"photo": ("a.txt", b"hello", "text/plain")}).status_code == 415
    big = {"photo": ("big.jpg", b"x" * (disease.MAX_BYTES + 1), "image/jpeg")}
    assert client.post("/disease/check", files=big).status_code == 413


def test_photo_check_reports_checker_down(client, monkeypatch):
    login(client)
    monkeypatch.setattr(settings, "disease_url", "http://127.0.0.1:9")  # nothing listens on port 9
    r = client.post("/disease/check", files=PHOTO)
    assert r.status_code == 503 and "not running" in r.json()["detail"]
