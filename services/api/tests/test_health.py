from fastapi.testclient import TestClient

from stentor.main import app


def test_health_ok():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "anthropic_configured" in body


def test_cors_allows_web_origin():
    r = TestClient(app).get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
