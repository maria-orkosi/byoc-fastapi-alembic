from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ready():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"ready": True}


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}