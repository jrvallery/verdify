from fastapi.testclient import TestClient

from app.main import app


def test_meta_sensor_kinds_includes_core():
    client = TestClient(app)
    r = client.get("/api/v1/meta/sensor-kinds")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    kinds = set(data.get("sensor_kinds", []))
    # Core kinds required by contract
    for k in ["temperature", "humidity", "vpd", "co2", "light"]:
        assert k in kinds


def test_validation_errors_use_standard_envelope():
    client = TestClient(app)
    # Register with invalid password (too short) to trigger 422 from Pydantic
    payload = {"email": "user@example.com", "password": "123"}
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 422
    body = r.json()
    # Standard envelope
    assert body["error_code"] == "E422_UNPROCESSABLE_ENTITY"
    assert body["message"] == "Validation error"
    assert "timestamp" in body
    assert "request_id" in body
    assert isinstance(body.get("details"), list)
    # Ensure a field error mentions password
    assert any("password" in (d.get("field") or "") for d in body["details"])
