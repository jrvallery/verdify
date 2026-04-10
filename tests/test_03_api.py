"""
Test 03: API — All endpoints respond correctly.
Tests the FastAPI application at api.verdify.ai via localhost.
"""

import json
import subprocess


def api_get(path: str, host: str = "api.verdify.ai") -> tuple[int, str]:
    """Hit the API via curl through Traefik."""
    result = subprocess.run(
        ["curl", "-sk", f"https://127.0.0.1{path}", "-H", f"Host: {host}", "-w", "\n%{http_code}"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    lines = result.stdout.strip().rsplit("\n", 1)
    body = lines[0] if len(lines) > 1 else ""
    status = int(lines[-1]) if lines[-1].isdigit() else 0
    return status, body


class TestAPIHealth:
    """API must be reachable and healthy."""

    def test_root_endpoint(self):
        status, body = api_get("/")
        assert status == 200, f"Root returned {status}"

    def test_health_endpoint(self):
        status, body = api_get("/api/v1/status")
        assert status == 200, f"Status returned {status}"
        data = json.loads(body)
        assert "status" in data or "ok" in body.lower()


class TestAPISetpoints:
    """Setpoint endpoint must return valid key=value data for ESP32."""

    @staticmethod
    def _parse_setpoints(body: str) -> dict:
        """Parse key=value format returned by /setpoints."""
        data = {}
        for line in body.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                try:
                    data[k.strip()] = float(v.strip())
                except ValueError:
                    data[k.strip()] = v.strip()
        return data

    def test_setpoints_endpoint(self):
        status, body = api_get("/setpoints")
        assert status == 200, f"Setpoints returned {status}"
        data = self._parse_setpoints(body)
        assert len(data) >= 10, f"Setpoints returned only {len(data)} params"

    def test_setpoints_has_required_params(self):
        status, body = api_get("/setpoints")
        data = self._parse_setpoints(body)
        required = ["temp_high", "temp_low", "vpd_high", "vpd_low"]
        for param in required:
            assert param in data, f"Setpoints missing {param}"

    def test_setpoints_values_sane(self):
        status, body = api_get("/setpoints")
        data = self._parse_setpoints(body)
        if "temp_high" in data and isinstance(data["temp_high"], float):
            assert 50 <= data["temp_high"] <= 100, f"temp_high={data['temp_high']} out of range"
        if "vpd_high" in data and isinstance(data["vpd_high"], float):
            assert 0.3 <= data["vpd_high"] <= 3.0, f"vpd_high={data['vpd_high']} out of range"


class TestAPICrops:
    """Crop catalog endpoints."""

    def test_crops_list(self):
        status, body = api_get("/api/v1/crops")
        assert status == 200, f"Crops returned {status}"
        data = json.loads(body)
        assert isinstance(data, list), "Crops should return a list"

    def test_crops_active(self):
        status, body = api_get("/api/v1/crops?active=true")
        assert status == 200


class TestAPIPlans:
    """Plan-related endpoints."""

    def test_active_plan(self):
        status, body = api_get("/api/v1/plan/active")
        assert status in (200, 404), f"Active plan returned {status}"
