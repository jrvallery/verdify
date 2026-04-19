"""Test 10: API mutation endpoints — validation boundaries.

Exercises POST/PUT/DELETE paths of api/main.py *without* writing production
state. Each test drives a failure mode (422 Pydantic rejection, 404 missing
row, 400 bad enum) so the request reaches the handler and the declared
request-body model / path validation fires, but never writes to DB.

Happy-path mutation coverage would require a sandbox DB, which CI doesn't
yet provide (see docs/backlog/cross-cutting.md — integration CI).
"""

from __future__ import annotations

import subprocess

MISSING_CROP_ID = 9999999


def _curl(method: str, path: str, body: str | None = None) -> tuple[int, str]:
    args = ["curl", "-sk", "-X", method, "-H", "Host: api.verdify.ai"]
    if body is not None:
        args += ["-H", "Content-Type: application/json", "-d", body]
    args += ["-w", "\n%{http_code}", f"https://127.0.0.1{path}"]
    r = subprocess.run(args, capture_output=True, text=True, timeout=10)
    lines = r.stdout.rstrip().rsplit("\n", 1)
    body_out = lines[0] if len(lines) > 1 else ""
    status = int(lines[-1]) if lines[-1].isdigit() else 0
    return status, body_out


class TestCropMutations:
    def test_create_crop_empty_body_422(self):
        status, _ = _curl("POST", "/api/v1/crops", body="{}")
        assert status == 422, f"POST empty body expected 422, got {status}"

    def test_create_crop_missing_required_field_422(self):
        # CropCreate requires `name` (min_length=1) and `position`
        status, _ = _curl("POST", "/api/v1/crops", body='{"variety": "x"}')
        assert status == 422

    def test_create_crop_wrong_type_422(self):
        # All required fields present but `count` (int | None) gets a non-coercible string.
        status, _ = _curl(
            "POST",
            "/api/v1/crops",
            body=(
                '{"name": "x", "position": "X-1", "zone": "test", '
                '"stage": "seed", "planted_date": "2026-01-01", "count": "not-a-number"}'
            ),
        )
        assert status == 422

    def test_update_missing_crop_404(self):
        status, _ = _curl("PUT", f"/api/v1/crops/{MISSING_CROP_ID}", body='{"stage": "seed"}')
        assert status == 404

    def test_delete_missing_crop_404(self):
        status, _ = _curl("DELETE", f"/api/v1/crops/{MISSING_CROP_ID}")
        assert status == 404


class TestObservationMutations:
    def test_create_observation_on_missing_crop_404(self):
        status, _ = _curl(
            "POST",
            f"/api/v1/crops/{MISSING_CROP_ID}/observations",
            body='{"obs_type": "note", "notes": "test"}',
        )
        assert status == 404

    def test_create_observation_unknown_field_422(self):
        # ObservationCreate has model_config = ConfigDict(extra="forbid"); an
        # unknown key rejects at the Pydantic layer before the handler runs.
        status, _ = _curl(
            "POST",
            f"/api/v1/crops/{MISSING_CROP_ID}/observations",
            body='{"bogus_field": "x"}',
        )
        assert status == 422


class TestEventMutations:
    def test_create_event_on_missing_crop_404(self):
        status, _ = _curl(
            "POST",
            f"/api/v1/crops/{MISSING_CROP_ID}/events",
            body='{"event_type": "note"}',
        )
        assert status == 404

    def test_create_event_empty_body_422(self):
        status, _ = _curl("POST", f"/api/v1/crops/{MISSING_CROP_ID}/events", body="{}")
        assert status == 422


class TestLightControl:
    def test_bad_circuit_400(self):
        status, _ = _curl("POST", "/api/v1/greenhouses/vallery/lights/bogus/on")
        assert status == 400

    def test_bad_action_400(self):
        status, _ = _curl("POST", "/api/v1/greenhouses/vallery/lights/main/bogus")
        assert status == 400
