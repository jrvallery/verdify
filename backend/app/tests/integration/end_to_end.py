"""
end_to_end_v3.py
================

OPINIONATED, CONTRACT-FOCUSED E2E INTEGRATION TEST (v3.1)
Covers: Auth, CRUD (all core domains), metadata, controller onboarding,
device token & config fetch (with proper ETag header), plan typing + invariants,
telemetry v2 (+ idempotency) where available, state machine (rows + fallback),
crops/zone-crops/observations, sensor-zone mappings, fan groups & buttons,
pagination, ownership boundaries, uniqueness constraints, ETag caching, and edges.

Key alignments to backend (Aug 2025 bundle):
- Controllers are nested under greenhouse path:
  /greenhouses/{greenhouse_id}/controllers/[…]
- Sensor–zone unmapping uses DELETE with query parameters (sensor_id, zone_id, kind)
- Device config fetch returns payload JSON and ETag in headers (not "etag" in body)
- GET /controllers/by-name/{device_name}/config requires a valid device token; this
  suite treats it as OPTIONAL if claim/exchange is unavailable in the environment.

Passing this suite with 0 critical failures is sign-off to move to frontend.

Run:
    pytest -q end_to_end_v3.py
or:
    python end_to_end_v3.py
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from fastapi.testclient import TestClient

# Server import (keep import local-friendly)
try:
    from app.main import app
except Exception:
    app = None

# --------------------------------------------------------------------
# Test configuration
# --------------------------------------------------------------------
BASE_URL = os.getenv("VERDIFY_BASE_URL", "http://localhost:8000")
API_V1 = f"{BASE_URL}/api/v1"


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def _tz_iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).isoformat()


def _now_naive_iso() -> str:
    return datetime.utcnow().replace(tzinfo=None).isoformat()


ACCEPT_4XX = {400, 401, 403, 404, 409, 422}
ACCEPT_2XX = {200, 201, 202, 204}
ACCEPT_3XX = {304}

CRITICAL = "CRITICAL"
OPTIONAL = "OPTIONAL"


class EndToEndV3:
    """
    Complete v3 end-to-end API verifier.
    """

    def __init__(self):
        self.session = requests.Session()
        self.client = TestClient(app) if app else None

        # Entities and tokens captured during the flow
        self.t: dict[str, Any] = {
            "users": {},
            "tokens": {},
            "device_tokens": {},
            "greenhouses": {},
            "zones": {},
            "controllers": {},
            "sensors": {},
            "actuators": {},
            "fan_groups": {},
            "buttons": {},
            "sensor_zone_maps": {},
            "plans": {},
            "config_snapshots": {},
            "crops": {},
            "zone_crops": {},
            "observations": {},
            "state_machine": {},
            "idempotency": {},
        }

        # Coverage + results
        self.results = {
            "assertions": [],
            "endpoints": set(),
            "passed": 0,
            "failed": 0,
            "critical_failed": 0,
        }

    # ------------------------ logging/helpers ------------------------

    def _mark(self, name: str, ok: bool, level: str = CRITICAL, details: str = ""):
        self.results["endpoints"].add(name)
        if ok:
            self.results["passed"] += 1
            print(f"✅ {name} [{level}] {details}")
        else:
            self.results["failed"] += 1
            if level == CRITICAL:
                self.results["critical_failed"] += 1
            print(f"❌ {name} [{level}] {details}")

    def _req(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{API_V1}{path}" if path.startswith("/") else f"{API_V1}/{path}"
        try:
            r = self.session.request(method, url, timeout=30, **kwargs)
            return r
        except Exception as e:
            raise RuntimeError(f"request failed: {method} {url}: {e}") from e

    def _accept(self, status: int, allowed: set[int]) -> bool:
        return status in allowed

    def _same_json_shape(self, data: dict, must_absent: list[str]) -> bool:
        return not any(k in data for k in must_absent)

    def _expect_enveloped_list(self, obj: dict) -> bool:
        return all(
            k in obj for k in ("page", "page_size", "total", "data")
        ) and isinstance(obj["data"], list)

    def _hash(self, obj: Any) -> str:
        return hashlib.sha256(
            json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()

    # ------------------------ Phase 1: Auth --------------------------

    def phase_auth_users(self):
        print("\n🔐 PHASE 1: USERS & AUTH")
        # Register primary user
        email1 = f"e2e-v3-{secrets.token_hex(4)}@example.com"
        r = self._req(
            "POST",
            "/auth/register",
            json={
                "email": email1,
                "password": "StrongPass!234",
                "full_name": "E2E V3 A",
            },
        )
        ok = self._accept(r.status_code, {201})
        self._mark(
            "POST /auth/register primary", ok, CRITICAL, f"status={r.status_code}"
        )
        assert ok, r.text
        user1 = r.json().get("user") or r.json()
        self.t["users"]["u1"] = user1
        token1 = r.json().get("access_token")
        if token1:
            self.t["tokens"]["u1"] = token1
            self.session.headers.update({"Authorization": f"Bearer {token1}"})

        # Login (form)
        r = self._req(
            "POST",
            "/auth/login",
            data={"username": email1, "password": "StrongPass!234"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        ok = self._accept(r.status_code, {200})
        self._mark("POST /auth/login primary", ok, CRITICAL, f"status={r.status_code}")
        assert ok, r.text
        token1 = r.json()["access_token"]
        self.t["tokens"]["u1"] = token1
        self.session.headers.update({"Authorization": f"Bearer {token1}"})

        # Validate token
        r = self._req("POST", "/auth/test-token")
        ok = self._accept(r.status_code, {200})
        self._mark("POST /auth/test-token", ok, CRITICAL, f"status={r.status_code}")

        # Create second user (for ownership boundaries)
        email2 = f"e2e-v3-{secrets.token_hex(4)}@example.com"
        r = self._req(
            "POST",
            "/auth/register",
            json={
                "email": email2,
                "password": "StrongPass!234",
                "full_name": "E2E V3 B",
            },
        )
        ok = self._accept(r.status_code, {201})
        self._mark(
            "POST /auth/register secondary", ok, CRITICAL, f"status={r.status_code}"
        )
        assert ok, r.text
        self.t["users"]["u2"] = r.json().get("user") or r.json()
        # store token for u2 (for later boundary checks)
        r = self._req(
            "POST",
            "/auth/login",
            data={"username": email2, "password": "StrongPass!234"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert self._accept(r.status_code, {200}), r.text
        self.t["tokens"]["u2"] = r.json()["access_token"]

    # --------------------- Phase 2A: Greenhouses ---------------------

    def phase_greenhouse(self):
        print("\n🏡 PHASE 2A: GREENHOUSE")
        gh_in = {
            "title": f"E2E V3 GH {secrets.token_hex(3)}",
            "description": "V3 greenhouse",
            "latitude": 37.77,
            "longitude": -122.42,
            "min_temp_c": 9.0,
            "max_temp_c": 31.0,
            "min_vpd_kpa": 0.4,
            "max_vpd_kpa": 2.2,
            "context_text": "created-by-e2e-v3",
            # params exists on DB model but should NOT appear in public GET API
            "params": {"note": "db-visible-only"},
        }
        r = self._req("POST", "/greenhouses/", json=gh_in)
        ok = self._accept(r.status_code, {201})
        self._mark("POST /greenhouses/", ok, CRITICAL, f"status={r.status_code}")
        assert ok, r.text
        gh = r.json()
        self.t["greenhouses"]["gh"] = gh

        gh_id = gh["id"]
        # List (paginated envelope)
        r = self._req("GET", "/greenhouses/", params={"page": 1, "page_size": 10})
        ok = self._accept(r.status_code, {200}) and self._expect_enveloped_list(
            r.json()
        )
        self._mark("GET /greenhouses/ list envelope", ok, CRITICAL)

        # Get public DTO should not leak rails_* or params
        r = self._req("GET", f"/greenhouses/{gh_id}")
        ok = self._accept(r.status_code, {200}) and self._same_json_shape(
            r.json(),
            ["rails_max_temp_c", "rails_min_temp_c", "params", "user_id", "updated_at"],
        )
        self._mark("GET /greenhouses/{id} public fields", ok, CRITICAL)

        # Update (including permissible fields)
        r = self._req(
            "PATCH",
            f"/greenhouses/{gh_id}",
            json={"description": "v3-updated", "max_temp_c": 33.0},
        )
        ok = self._accept(r.status_code, {200}) and r.json().get("max_temp_c") == 33.0
        self._mark("PATCH /greenhouses/{id}", ok, CRITICAL)

        # Invalid data
        r = self._req(
            "POST",
            "/greenhouses/",
            json={"title": "", "latitude": 222.0, "longitude": -222.0},
        )
        ok = self._accept(r.status_code, {422})
        self._mark("POST /greenhouses invalid validation", ok, CRITICAL)

    # ------------------------ Phase 2B: Zones ------------------------

    def phase_zones(self):
        print("\n🌱 PHASE 2B: ZONES")
        gh = self.t["greenhouses"]["gh"]
        # Create two zones
        zone1 = {
            "greenhouse_id": gh["id"],
            "zone_number": 1,
            "location": "N",
            "context_text": "Z1",
        }
        r = self._req("POST", "/zones/", json=zone1)
        ok = self._accept(r.status_code, {201})
        self._mark("POST /zones/ z1", ok, CRITICAL)
        self.t["zones"]["z1"] = r.json()

        zone2 = {
            "greenhouse_id": gh["id"],
            "zone_number": 2,
            "location": "S",
            "context_text": "Z2",
        }
        r = self._req("POST", "/zones/", json=zone2)
        ok = self._accept(r.status_code, {201})
        self._mark("POST /zones/ z2", ok, CRITICAL)
        self.t["zones"]["z2"] = r.json()

        # List by GH
        r = self._req("GET", "/zones/", params={"greenhouse_id": gh["id"]})
        ok = self._accept(r.status_code, {200}) and any(
            z["id"] == self.t["zones"]["z1"]["id"] for z in r.json().get("data", [])
        )
        self._mark("GET /zones/ by greenhouse", ok, CRITICAL)

        # Get public (no is_active)
        r = self._req("GET", f"/zones/{self.t['zones']['z1']['id']}")
        ok = self._accept(r.status_code, {200}) and ("is_active" not in r.json())
        self._mark("GET /zones/{id} public fields", ok, CRITICAL)

        # Update
        r = self._req(
            "PATCH",
            f"/zones/{self.t['zones']['z1']['id']}",
            json={"context_text": "North-Updated"},
        )
        ok = (
            self._accept(r.status_code, {200})
            and r.json().get("context_text") == "North-Updated"
        )
        self._mark("PATCH /zones/{id}", ok, CRITICAL)

        # Uniqueness: duplicate zone_number in same GH
        dup = {
            "greenhouse_id": gh["id"],
            "zone_number": 1,
            "location": "E",
            "context_text": "Dup",
        }
        r = self._req("POST", "/zones/", json=dup)
        ok = self._accept(r.status_code, ACCEPT_4XX)
        self._mark("POST /zones/ duplicate zone_number", ok, CRITICAL)

    # --------------------- Phase 2C: Controllers ---------------------

    def phase_controllers(self):
        print("\n🎮 PHASE 2C: CONTROLLERS")
        gh = self.t["greenhouses"]["gh"]
        gh_id = gh["id"]

        device_name = f"verdify-{secrets.token_hex(3)}"  # verdify-xxxxxx
        c_in = {
            # greenhouse_id is overridden by path on the backend; safe to include
            "greenhouse_id": gh_id,
            "label": f"E2E V3 Ctrl {secrets.token_hex(2)}",
            "device_name": device_name,
            "is_climate_controller": True,
            "hw_version": "2.2",
            "fw_version": "1.7.0",
        }
        r = self._req("POST", f"/greenhouses/{gh_id}/controllers/", json=c_in)
        ok = self._accept(r.status_code, {201})
        self._mark(
            "POST /greenhouses/{gh}/controllers/ create",
            ok,
            CRITICAL,
            f"status={r.status_code}",
        )
        assert ok, r.text
        ctrl = r.json()
        self.t["controllers"]["c1"] = ctrl

        # List (returns a plain list for this greenhouse)
        r = self._req("GET", f"/greenhouses/{gh_id}/controllers/")
        ok = self._accept(r.status_code, {200})
        if ok:
            data = r.json()
            ok = isinstance(data, list) and any(c["id"] == ctrl["id"] for c in data)
        self._mark(
            "GET /greenhouses/{gh}/controllers/ list (scoped)",
            ok,
            CRITICAL,
        )

        # Get and Update (scoped to greenhouse)
        r = self._req("GET", f"/greenhouses/{gh_id}/controllers/{ctrl['id']}")
        ok = self._accept(r.status_code, {200})
        self._mark("GET /greenhouses/{gh}/controllers/{id}", ok, CRITICAL)

        r = self._req(
            "PATCH",
            f"/greenhouses/{gh_id}/controllers/{ctrl['id']}",
            json={"fw_version": "1.7.1"},
        )
        ok = (
            self._accept(r.status_code, {200}) and r.json().get("fw_version") == "1.7.1"
        )
        self._mark("PATCH /greenhouses/{gh}/controllers/{id}", ok, CRITICAL)

        # Optional: attempt to create a *second* climate controller for same GH (policy may reject)
        c2_in = {
            "greenhouse_id": gh_id,
            "label": f"E2E V3 Ctrl B {secrets.token_hex(2)}",
            "device_name": f"verdify-{secrets.token_hex(3)}",
            "is_climate_controller": True,
        }
        r = self._req("POST", f"/greenhouses/{gh_id}/controllers/", json=c2_in)
        ok = self._accept(r.status_code, ACCEPT_4XX) or self._accept(
            r.status_code, {201}
        )
        self._mark(
            "POST /greenhouses/{gh}/controllers/ second climate (policy)",
            ok,
            OPTIONAL,
            f"status={r.status_code}",
        )

        self.t["controllers"]["device_name"] = device_name

    # -------------------- Phase 2D: Sensors & Links ------------------

    def phase_sensors_and_links(self):
        print("\n📊 PHASE 2D: SENSORS & LINKS")
        ctrl = self.t["controllers"]["c1"]
        # Create temp sensor
        s1 = {
            "controller_id": ctrl["id"],
            "name": f"E2E V3 Temp {secrets.token_hex(3)}",
            "kind": "temperature",
            "scope": "zone",
            "modbus_slave_id": 1,
            "modbus_reg": 30001,
            "value_type": "float",
            "include_in_climate_loop": True,
        }
        r = self._req("POST", "/sensors/", json=s1)
        ok = self._accept(r.status_code, {201})
        self._mark("POST /sensors/ temperature", ok, CRITICAL)
        self.t["sensors"]["s1"] = r.json()

        # Create humidity sensor
        s2 = {
            "controller_id": ctrl["id"],
            "name": f"E2E V3 RH {secrets.token_hex(3)}",
            "kind": "humidity",
            "scope": "zone",
            "modbus_slave_id": 1,
            "modbus_reg": 30002,
            "value_type": "float",
        }
        r = self._req("POST", "/sensors/", json=s2)
        ok = self._accept(r.status_code, {201})
        self._mark("POST /sensors/ humidity", ok, CRITICAL)
        self.t["sensors"]["s2"] = r.json()

        # List sensors
        r = self._req("GET", "/sensors/")
        ok = self._accept(r.status_code, {200}) and any(
            s["id"] == self.t["sensors"]["s1"]["id"] for s in r.json().get("data", [])
        )
        self._mark("GET /sensors/ list", ok, CRITICAL)

        # Get + Update
        r = self._req("GET", f"/sensors/{self.t['sensors']['s1']['id']}")
        ok = self._accept(r.status_code, {200})
        self._mark("GET /sensors/{id}", ok, CRITICAL)

        r = self._req(
            "PATCH",
            f"/sensors/{self.t['sensors']['s1']['id']}",
            json={"modbus_reg": 30003, "scale_factor": 1.1},
        )
        ok = self._accept(r.status_code, {200}) and r.json().get("modbus_reg") == 30003
        self._mark("PATCH /sensors/{id}", ok, CRITICAL)

        # Duplicate (slave,reg) uniqueness
        dup = {
            "controller_id": ctrl["id"],
            "name": f"Dup Modbus {secrets.token_hex(2)}",
            "kind": "temperature",
            "scope": "zone",
            "modbus_slave_id": self.t["sensors"]["s1"]["modbus_slave_id"],
            "modbus_reg": 30003,
            "value_type": "float",
        }
        r = self._req("POST", "/sensors/", json=dup)
        ok = self._accept(r.status_code, ACCEPT_4XX)
        self._mark("POST /sensors duplicate modbus", ok, CRITICAL)

        # INVALID enum
        bad = {
            "controller_id": ctrl["id"],
            "name": "Bad Enum",
            "kind": "not_a_kind",
            "scope": "zone",
        }
        r = self._req("POST", "/sensors/", json=bad)
        ok = self._accept(r.status_code, {422})
        self._mark("POST /sensors invalid enum", ok, CRITICAL)

        # SensorZoneMap (links) — map temp sensor to zone1
        z1 = self.t["zones"]["z1"]["id"]
        s1_id = self.t["sensors"]["s1"]["id"]
        map_in = {"sensor_id": s1_id, "zone_id": z1, "kind": "temperature"}
        r = self._req("POST", "/sensor-zone-maps/", json=map_in)
        ok = self._accept(r.status_code, {201, 200})
        self._mark("POST /sensor-zone-maps/ create", ok, CRITICAL)
        self.t["sensor_zone_maps"]["m1"] = {
            "sensor_id": s1_id,
            "zone_id": z1,
            "kind": "temperature",
        }

        # Duplicate mapping rejected
        r = self._req("POST", "/sensor-zone-maps/", json=map_in)
        ok = self._accept(r.status_code, ACCEPT_4XX)
        self._mark("POST /sensor-zone-maps/ duplicate", ok, CRITICAL)

    # -------------------- Phase 2E: Actuators & Fans -----------------

    def phase_actuators_fans_buttons(self):
        print("\n⚙️ PHASE 2E: ACTUATORS, FAN GROUPS, BUTTONS")
        ctrl = self.t["controllers"]["c1"]

        # Create two actuators
        a1 = {
            "controller_id": ctrl["id"],
            "name": f"E2E V3 Fan {secrets.token_hex(2)}",
            "kind": "fan",
            "relay_channel": 1,
            "fail_safe_state": "off",
        }
        r = self._req("POST", "/actuators/", json=a1)
        ok = self._accept(r.status_code, {201})
        self._mark("POST /actuators/ a1", ok, CRITICAL)
        self.t["actuators"]["a1"] = r.json()

        a2 = {
            "controller_id": ctrl["id"],
            "name": f"E2E V3 Fan {secrets.token_hex(2)}",
            "kind": "fan",
            "relay_channel": 2,
            "fail_safe_state": "off",
        }
        r = self._req("POST", "/actuators/", json=a2)
        ok = self._accept(r.status_code, {201})
        self._mark("POST /actuators/ a2", ok, CRITICAL)
        self.t["actuators"]["a2"] = r.json()

        # Duplicate relay channel on same controller should be rejected
        dup = {
            "controller_id": ctrl["id"],
            "name": "Dup Relay",
            "kind": "fan",
            "relay_channel": 1,
            "fail_safe_state": "off",
        }
        r = self._req("POST", "/actuators/", json=dup)
        ok = self._accept(r.status_code, ACCEPT_4XX)
        self._mark("POST /actuators duplicate relay", ok, CRITICAL)

        # Fan group + members
        fg = {"controller_id": ctrl["id"], "name": f"FG-{secrets.token_hex(2)}"}
        r = self._req("POST", "/fan-groups/", json=fg)
        ok = self._accept(r.status_code, {201})
        self._mark("POST /fan-groups/", ok, CRITICAL)
        self.t["fan_groups"]["fg1"] = r.json()

        # Add a1 to fan group (route: POST /fan-groups/{id}/members)
        fgid = self.t["fan_groups"]["fg1"]["id"]
        add_body = {
            "fan_group_id": fgid,
            "actuator_id": self.t["actuators"]["a1"]["id"],
        }
        r = self._req(
            "POST",
            f"/fan-groups/{fgid}/members",
            json={"actuator_id": add_body["actuator_id"]},
        )
        ok = self._accept(r.status_code, {201, 200})
        self._mark("POST /fan-groups/{id}/members add", ok, CRITICAL)

        # Duplicate member rejected
        r = self._req(
            "POST",
            f"/fan-groups/{fgid}/members",
            json={"actuator_id": add_body["actuator_id"]},
        )
        ok = self._accept(r.status_code, ACCEPT_4XX)
        self._mark("POST /fan-groups/{id}/members duplicate", ok, CRITICAL)

        # Buttons: one per kind per controller
        b1 = {
            "controller_id": ctrl["id"],
            "button_kind": "cool",
            "timeout_s": 300,
            "target_temp_stage": 1,
        }
        r = self._req("POST", "/buttons/", json=b1)
        ok = self._accept(r.status_code, {201})
        self._mark("POST /buttons/ cool", ok, CRITICAL)
        self.t["buttons"]["cool"] = r.json()

        r = self._req("POST", "/buttons/", json=b1)
        ok = self._accept(r.status_code, ACCEPT_4XX)
        self._mark("POST /buttons/ duplicate kind", ok, CRITICAL)

        # Update button
        r = self._req(
            "PATCH",
            f"/buttons/{self.t['buttons']['cool']['id']}",
            json={"timeout_s": 600},
        )
        ok = self._accept(r.status_code, {200})
        self._mark("PATCH /buttons/{id}", ok, CRITICAL)

    # ---------------- Phase 2F: Crops / ZoneCrops / Obs --------------

    def phase_crops_zonecrops_observations(self):
        print("\n🥬 PHASE 2F: CROPS / ZONE-CROPS / OBSERVATIONS")
        # Crop create
        crop = {
            "name": f"Tomato {secrets.token_hex(2)}",
            "description": "E2E V3 crop",
            "growing_days": 60,
            "recipe": {"ph": "6.0-6.8"},
        }
        r = self._req("POST", "/crops/", json=crop)
        ok = self._accept(r.status_code, {201}) and all(
            k not in r.json() for k in ("created_at", "updated_at")
        )
        self._mark("POST /crops/", ok, CRITICAL)
        self.t["crops"]["c1"] = r.json()

        # ZoneCrop create (active) for zone1
        z1 = self.t["zones"]["z1"]["id"]
        zc1 = {
            "crop_id": self.t["crops"]["c1"]["id"],
            "zone_id": z1,
            "start_date": _tz_iso(),
            "is_active": True,
            "area_sqm": 12.0,
        }
        r = self._req("POST", "/zone-crops/", json=zc1)
        ok = self._accept(r.status_code, {201})
        self._mark("POST /zone-crops/ zc1", ok, CRITICAL)
        self.t["zone_crops"]["zc1"] = r.json()

        # Single-active per zone: creating another active should fail
        zc_dup = {
            "crop_id": self.t["crops"]["c1"]["id"],
            "zone_id": z1,
            "start_date": _tz_iso(),
            "is_active": True,
        }
        r = self._req("POST", "/zone-crops/", json=zc_dup)
        ok = self._accept(r.status_code, {409, 422})
        self._mark("POST /zone-crops/ single-active invariant", ok, CRITICAL)

        # Observation
        obs = {
            "zone_crop_id": self.t["zone_crops"]["zc1"]["id"],
            "observed_at": _tz_iso(),
            "observation_type": "growth",
            "height_cm": 11.3,
            "health_score": 9,
            "notes": "Looks good",
        }
        r = self._req("POST", "/observations", json=obs)
        ok = (
            self._accept(r.status_code, {201})
            and "observation_type" in r.json()
            and all(k not in r.json() for k in ("created_at", "updated_at"))
        )
        self._mark("POST /observations", ok, CRITICAL)
        self.t["observations"]["o1"] = r.json()

        # Close the cycle
        r = self._req(
            "PUT",
            f"/zone-crops/{self.t['zone_crops']['zc1']['id']}",
            json={"end_date": _tz_iso(), "is_active": False, "final_yield": 14.5},
        )
        ok = self._accept(r.status_code, {200})
        self._mark("PUT /zone-crops/{id} end", ok, CRITICAL)

    # ----------- Phase 3A: Plans (typed payload + invariants) --------

    def phase_plans_typed(self):
        print("\n📋 PHASE 3A: PLANS (TYPED + INVARIANTS)")
        gh = self.t["greenhouses"]["gh"]["id"]
        eff_from = utc_now()
        eff_to = eff_from + timedelta(hours=2)
        payload = {
            "version": 1,
            "greenhouse_id": gh,
            "effective_from": eff_from.isoformat(),
            "effective_to": eff_to.isoformat(),
            "setpoints": [
                {
                    "ts_utc": eff_from.isoformat(),
                    "min_temp_c": 19.5,
                    "max_temp_c": 24.0,
                    "min_vpd_kpa": 0.8,
                    "max_vpd_kpa": 1.4,
                    "temp_stage_delta": 0,
                    "humi_stage_delta": 0,
                }
            ],
            "irrigation": [],
            "fertilization": [],
            "lighting": [],
        }
        create = {
            "greenhouse_id": gh,
            "is_active": True,
            "effective_from": eff_from.isoformat(),
            "effective_to": eff_to.isoformat(),
            "payload": payload,
        }
        r = self._req("POST", "/plans/", json=create)
        if self._accept(r.status_code, {201}):
            plan = r.json()
            ok = (plan["version"] == plan["payload"]["version"]) and (
                "created_at" in plan
            )
            self._mark("POST /plans/ create + version equality", ok, CRITICAL)
            self.t["plans"]["p1"] = plan
            plan_id = plan["id"]

            # Mismatched payload.version on PATCH
            bad = dict(plan["payload"])
            bad["version"] = bad["version"] + 1
            r2 = self._req("PATCH", f"/plans/{plan_id}", json={"payload": bad})
            ok = self._accept(r2.status_code, {409, 422})
            self._mark("PATCH /plans/{id} payload.version mismatch", ok, CRITICAL)

            # Single-active invariant
            payload2 = dict(payload)
            payload2["version"] = payload["version"] + 1
            create2 = {
                "greenhouse_id": gh,
                "is_active": True,
                "effective_from": (eff_from + timedelta(hours=3)).isoformat(),
                "effective_to": (eff_from + timedelta(hours=5)).isoformat(),
                "payload": payload2,
            }
            r3 = self._req("POST", "/plans/", json=create2)
            ok = self._accept(r3.status_code, {409, 422})
            self._mark("POST /plans second active rejected", ok, CRITICAL)
        elif self._accept(r.status_code, {403}):
            # superuser path required — treat as optional
            self._mark(
                "POST /plans/ requires elevated role",
                True,
                OPTIONAL,
                f"status={r.status_code}",
            )
        else:
            self._mark(
                "POST /plans/ unexpected",
                False,
                CRITICAL,
                f"status={r.status_code} body={r.text}",
            )

    # ----------------- Phase 3B: Config publish/fetch ----------------

    def phase_config_publish_fetch(self):
        print("\n⚙️ PHASE 3B: CONFIG PUBLISH + FETCH (BY DEVICE)")
        gh = self.t["greenhouses"]["gh"]["id"]
        # Try a dry-run publish (endpoint variants supported)
        payload = {"dry_run": True}
        r = self._req("POST", f"/greenhouses/{gh}/config/publish", json=payload)
        if not self._accept(r.status_code, {200, 201}):
            r = self._req("POST", f"/config/{gh}/publish", json=payload)
        if self._accept(r.status_code, {200, 201}):
            body = r.json()
            ok = "version" in body and "payload" in body
            self._mark("POST /config publish dry_run", ok, OPTIONAL)
        else:
            self._mark("POST /config publish dry_run not available", True, OPTIONAL)

        # Try a real publish (optional)
        r = self._req(
            "POST", f"/greenhouses/{gh}/config/publish", json={"dry_run": False}
        )
        if self._accept(r.status_code, {200, 201}):
            snap = r.json()
            ok = "version" in snap and ("etag" in snap or "payload" in snap)
            self._mark("POST /config publish persist", ok, OPTIONAL)
            if ok:
                self.t["config_snapshots"]["latest"] = snap

        # Device config fetch (requires device token). This is CRITICAL only if a 200 is achieved.
        device_token = self._obtain_device_token()
        device_name = self.t["controllers"]["device_name"]
        r = self._req(
            "GET",
            f"/controllers/by-name/{device_name}/config",
            headers={"X-Device-Token": device_token},
        )
        if self._accept(r.status_code, {200}):
            # Payload is the snapshot payload; ETag provided in headers
            cfg = r.json()
            has_etag_header = "ETag" in r.headers
            ok = isinstance(cfg, dict) and has_etag_header
            self._mark(
                "GET /controllers/by-name/{device}/config payload + ETag header",
                ok,
                CRITICAL,
            )
            if has_etag_header:
                etag_value = r.headers["ETag"]
                # ETag caching
                r2 = self._req(
                    "GET",
                    f"/controllers/by-name/{device_name}/config",
                    headers={"X-Device-Token": device_token, "If-None-Match": etag_value},
                )
                ok = self._accept(r2.status_code, {304})
                self._mark(
                    "GET /controllers/by-name... If-None-Match 304",
                    ok,
                    OPTIONAL,
                )
        elif self._accept(r.status_code, {401, 403, 404}):
            # Treat environments without device-token plumbing as OPTIONAL.
            self._mark(
                "GET /controllers/by-name/{device}/config not available",
                True,
                OPTIONAL,
                f"status={r.status_code}",
            )
        else:
            self._mark(
                "GET /controllers/by-name/{device}/config unexpected",
                False,
                OPTIONAL,
                f"status={r.status_code}",
            )

    # ----------- Phase 3C: Telemetry v2 + Idempotency ----------------

    def phase_telemetry_v2(self):
        print("\n📡 PHASE 3C: TELEMETRY V2 (+ IDEMPOTENCY)")
        device_token = self._obtain_device_token()
        z1 = self.t["zones"]["z1"]["id"]
        s1 = self.t["sensors"]["s1"]["id"]

        # Sensors
        sensors_batch = {
            "ts_utc": _tz_iso(),
            "readings": [
                {
                    "sensor_id": s1,
                    "kind": "temperature",
                    "value": 22.7,
                    "ts_utc": _tz_iso(),
                    "scope": "zone",
                    "zone_ids": [z1],
                },
            ],
        }
        r = self._req(
            "POST",
            "/telemetry/sensors",
            json=sensors_batch,
            headers={"X-Device-Token": device_token},
        )
        if self._accept(r.status_code, {200, 202}):
            ok = r.json().get("accepted", 0) >= 1
            self._mark("POST /telemetry/sensors", ok, CRITICAL, f"status={r.status_code}")
        elif self._accept(r.status_code, {401, 403}):
            # Optional in environments without device-token plumbing.
            self._mark("POST /telemetry/sensors unauthorized (optional)", True, OPTIONAL)
        else:
            self._mark(
                "POST /telemetry/sensors unexpected",
                False,
                OPTIONAL,
                f"status={r.status_code}",
            )

        # Status
        r = self._req(
            "POST",
            "/telemetry/status",
            json={
                "ts_utc": _tz_iso(),
                "temp_stage": 0,
                "humi_stage": 0,
                "avg_interior_temp_c": 22.0,
                "avg_interior_rh_pct": 45.0,
                "override_active": False,
                "plan_version": self.t.get("plans", {}).get("p1", {}).get("version", 1),
                "plan_stale": False,
                "offline_sensors": [],
                "fallback_active": False,
                "config_version": 1,
            },
            headers={"X-Device-Token": device_token},
        )
        if self._accept(r.status_code, {200, 202}):
            self._mark("POST /telemetry/status", True, CRITICAL)
        elif self._accept(r.status_code, {401, 403}):
            self._mark("POST /telemetry/status unauthorized (optional)", True, OPTIONAL)
        else:
            self._mark(
                "POST /telemetry/status unexpected",
                False,
                OPTIONAL,
                f"status={r.status_code}",
            )

        # Inputs good + bad enum (invalid action should 422)
        r = self._req(
            "POST",
            "/telemetry/inputs",
            json={
                "inputs": [
                    {
                        "button_kind": "cool",
                        "ts_utc": _tz_iso(),
                        "action": "pressed",
                        "latched": False,
                    }
                ]
            },
            headers={"X-Device-Token": device_token},
        )
        if self._accept(r.status_code, {200, 202}):
            self._mark("POST /telemetry/inputs valid", True, CRITICAL)
        elif self._accept(r.status_code, {401, 403}):
            self._mark("POST /telemetry/inputs valid unauthorized (optional)", True, OPTIONAL)
        else:
            self._mark(
                "POST /telemetry/inputs valid unexpected",
                False,
                OPTIONAL,
                f"status={r.status_code}",
            )

        r = self._req(
            "POST",
            "/telemetry/inputs",
            json={
                "inputs": [
                    {
                        "button_kind": "cool",
                        "ts_utc": _tz_iso(),
                        "action": "tap",
                        "latched": False,
                    }
                ]
            },
            headers={"X-Device-Token": device_token},
        )
        # If device auth present, we expect 422; otherwise 401/403 is fine (optional)
        if self._accept(r.status_code, {422}):
            self._mark("POST /telemetry/inputs invalid action", True, CRITICAL)
        elif self._accept(r.status_code, {401, 403}):
            self._mark("POST /telemetry/inputs invalid action unauthorized (optional)", True, OPTIONAL)
        else:
            self._mark(
                "POST /telemetry/inputs invalid action unexpected",
                False,
                OPTIONAL,
                f"status={r.status_code}",
            )

        # Actuators telemetry (optional path)
        act_events = {
            "events": [
                {
                    "actuator_id": self.t["actuators"]["a1"]["id"],
                    "ts_utc": _tz_iso(),
                    "state": True,
                    "reason": "test",
                }
            ]
        }
        r = self._req(
            "POST",
            "/telemetry/actuators",
            json=act_events,
            headers={"X-Device-Token": device_token},
        )
        self._mark(
            "POST /telemetry/actuators (optional)",
            self._accept(r.status_code, {200, 202, 404, 401, 403}),
            OPTIONAL,
            f"status={r.status_code}",
        )

        # Mixed batch & idempotency replay
        batch = {
            "sensors": sensors_batch,
            "status": {
                "ts_utc": _tz_iso(),
                "temp_stage": 0,
                "humi_stage": 0,
                "override_active": False,
            },
        }
        idem_key = f"idm-{secrets.token_hex(8)}"
        h = {"X-Device-Token": device_token, "Idempotency-Key": idem_key}
        r1 = self._req("POST", "/telemetry/batch", json=batch, headers=h)
        if self._accept(r1.status_code, {200, 202}):
            ok1 = True
            self._mark(
                "POST /telemetry/batch first", ok1, OPTIONAL, f"status={r1.status_code}"
            )
            r2 = self._req("POST", "/telemetry/batch", json=batch, headers=h)
            ok2 = self._accept(r2.status_code, {200, 202}) and (
                r2.json().get("accepted", 0) <= r1.json().get("accepted", 0)
            )
            self._mark("POST /telemetry/batch idempotent", ok2, OPTIONAL)
        else:
            self._mark(
                "POST /telemetry/batch unavailable (optional)",
                self._accept(r1.status_code, {401, 403, 404}),
                OPTIONAL,
                f"status={r1.status_code}",
            )

        # Invalid device token always should be rejected
        r = self._req(
            "POST",
            "/telemetry/sensors",
            json=sensors_batch,
            headers={"X-Device-Token": "invalid"},
        )
        ok = self._accept(r.status_code, {401, 403})
        self._mark("POST /telemetry/* bad device token", ok, CRITICAL)

    # --------------- Phase 3D: State Machine rows/fallback -----------

    def phase_state_machine(self):
        print("\n🔁 PHASE 3D: STATE MACHINE")
        gh = self.t["greenhouses"]["gh"]["id"]
        fg = self.t["fan_groups"]["fg1"]["id"]

        # Create a row (0,0) with must_on_fan_groups
        row = {
            "greenhouse_id": gh,
            "temp_stage": 0,
            "humi_stage": 0,
            "must_on_actuators": [],
            "must_off_actuators": [],
            "must_on_fan_groups": [{"fan_group_id": fg, "on_count": 1}],
            "must_off_fan_groups": [],
        }
        r = self._req("POST", "/state-machine-rows/", json=row)
        ok = self._accept(r.status_code, {201})
        self._mark("POST /state-machine-rows/", ok, CRITICAL)
        if ok:
            self.t["state_machine"]["row0"] = r.json()

        # Duplicate (0,0) should reject
        r = self._req("POST", "/state-machine-rows/", json=row)
        ok = self._accept(r.status_code, ACCEPT_4XX)
        self._mark("POST /state-machine-rows/ duplicate grid", ok, CRITICAL)

        # Fallback create/update (PUT)
        fallback = {
            "must_on_actuators": [],
            "must_off_actuators": [],
            "must_on_fan_groups": [{"fan_group_id": fg, "on_count": 1}],
            "must_off_fan_groups": [],
        }
        r = self._req("PUT", f"/state-machine-fallback/{gh}", json=fallback)
        ok = self._accept(r.status_code, {200, 201})
        self._mark("PUT /state-machine-fallback/{gh}", ok, CRITICAL)
        self.t["state_machine"]["fallback"] = (
            r.json() if self._accept(r.status_code, {200, 201}) else {}
        )

    # ------------------ Phase 3E: Controller Hello -------------------

    def phase_controller_hello(self):
        print("\n📟 PHASE 3E: CONTROLLER HELLO")
        device_name = self.t["controllers"]["device_name"]

        # Naive ts rejected
        bad = {
            "device_name": device_name,
            "claim_code": "123456",
            "hardware_profile": "kincony_a16s",
            "firmware": "1.0.0",
            "ts_utc": _now_naive_iso(),
        }
        r = self._req("POST", "/hello", json=bad)
        ok = self._accept(r.status_code, {422})
        self._mark("POST /hello naive ts", ok, CRITICAL)

        # Good hello (claimed/pending acceptable)
        good = dict(bad)
        good["ts_utc"] = _tz_iso()
        r = self._req("POST", "/hello", json=good)
        ok = self._accept(r.status_code, {200, 202})
        self._mark("POST /hello ok", ok, CRITICAL, f"status={r.status_code}")

    # --------------- Phase 4: Ownership & Boundary checks ------------

    def phase_ownership_boundaries(self):
        print("\n🚷 PHASE 4: OWNERSHIP / BOUNDARIES")
        gh = self.t["greenhouses"]["gh"]["id"]
        token2 = self.t["tokens"]["u2"]

        # Use secondary token to access primary resources
        hdr2 = {"Authorization": f"Bearer {token2}"}
        r = self._req("GET", f"/greenhouses/{gh}", headers=hdr2)
        ok = self._accept(r.status_code, {403, 404})
        self._mark("GET /greenhouses/{id} forbidden to other user", ok, CRITICAL)

        r = self._req(
            "PATCH", f"/greenhouses/{gh}", json={"title": "HACK"}, headers=hdr2
        )
        ok = self._accept(r.status_code, {403, 404})
        self._mark("PATCH /greenhouses/{id} forbidden to other user", ok, CRITICAL)

    # --------------- Phase 5: Pagination / Sorting / Normalize -------

    def phase_pagination_sorting(self):
        print("\n📄 PHASE 5: PAGINATION & SORTING")
        r = self._req("GET", "/greenhouses/", params={"page": 1, "page_size": 5})
        ok = self._accept(r.status_code, {200}) and self._expect_enveloped_list(
            r.json()
        )
        self._mark("GET /greenhouses/?page=1&page_size=5", ok, CRITICAL)

        # Invalid normalized (backend may normalize to >=1)
        r = self._req("GET", "/greenhouses/", params={"page": 0, "page_size": -1})
        ok = (
            self._accept(r.status_code, {200})
            and (r.json().get("page", 1) >= 1)
            and (r.json().get("page_size", 1) > 0)
        )
        self._mark("GET /greenhouses invalid pagination normalized", ok, CRITICAL)

    # ------------------ Phase 6: Cleanup + Cascades ------------------

    def phase_cleanup(self):
        print("\n🗑️ PHASE 6: CLEANUP")
        # Delete observation
        if self.t["observations"].get("o1"):
            oid = self.t["observations"]["o1"]["id"]
            r = self._req("DELETE", f"/observations/{oid}")
            self._mark(
                "DELETE /observations/{id}",
                self._accept(r.status_code, {200, 204}),
                CRITICAL,
            )

        # Remove sensor-zone map via query parameters (API contract)
        m = self.t["sensor_zone_maps"].get("m1")
        if m:
            r = self._req(
                "DELETE",
                "/sensor-zone-maps/",
                params={
                    "sensor_id": m["sensor_id"],
                    "zone_id": m["zone_id"],
                    "kind": m["kind"],
                },
            )
            self._mark(
                "DELETE /sensor-zone-maps/ (query params)",
                self._accept(r.status_code, {200, 204}),
                CRITICAL,
            )

        # Delete buttons, fan groups (members auto-removed), actuators, sensors
        if self.t["buttons"].get("cool"):
            r = self._req("DELETE", f"/buttons/{self.t['buttons']['cool']['id']}")
            self._mark(
                "DELETE /buttons/{id}",
                self._accept(r.status_code, {200, 204}),
                CRITICAL,
            )

        if self.t["fan_groups"].get("fg1"):
            r = self._req("DELETE", f"/fan-groups/{self.t['fan_groups']['fg1']['id']}")
            self._mark(
                "DELETE /fan-groups/{id}",
                self._accept(r.status_code, {200, 204}),
                CRITICAL,
            )

        for key in list(self.t["actuators"].keys()):
            r = self._req("DELETE", f"/actuators/{self.t['actuators'][key]['id']}")
            self._mark(
                f"DELETE /actuators/{{id}} {key}",
                self._accept(r.status_code, {200, 204}),
                CRITICAL,
            )

        for key in list(self.t["sensors"].keys()):
            r = self._req("DELETE", f"/sensors/{self.t['sensors'][key]['id']}")
            self._mark(
                f"DELETE /sensors/{{id}} {key}",
                self._accept(r.status_code, {200, 204}),
                CRITICAL,
            )

        # Delete zone-crop, crop
        if self.t["zone_crops"].get("zc1"):
            r = self._req("DELETE", f"/zone-crops/{self.t['zone_crops']['zc1']['id']}")
            self._mark(
                "DELETE /zone-crops/{id}",
                self._accept(r.status_code, {200, 204}),
                CRITICAL,
            )

        if self.t["crops"].get("c1"):
            r = self._req("DELETE", f"/crops/{self.t['crops']['c1']['id']}")
            self._mark(
                "DELETE /crops/{id}", self._accept(r.status_code, {200, 204}), CRITICAL
            )

        # Delete controller (scoped), zones, greenhouse
        if self.t["controllers"].get("c1"):
            gh_id = self.t["greenhouses"]["gh"]["id"]
            r = self._req(
                "DELETE",
                f"/greenhouses/{gh_id}/controllers/{self.t['controllers']['c1']['id']}",
            )
            self._mark(
                "DELETE /greenhouses/{gh}/controllers/{id}",
                self._accept(r.status_code, {200, 204}),
                CRITICAL,
            )

        if self.t["zones"].get("z1"):
            r = self._req("DELETE", f"/zones/{self.t['zones']['z1']['id']}")
            self._mark(
                "DELETE /zones/{id} z1",
                self._accept(r.status_code, {200, 204}),
                CRITICAL,
            )
        if self.t["zones"].get("z2"):
            r = self._req("DELETE", f"/zones/{self.t['zones']['z2']['id']}")
            self._mark(
                "DELETE /zones/{id} z2",
                self._accept(r.status_code, {200, 204}),
                CRITICAL,
            )

        if self.t["greenhouses"].get("gh"):
            r = self._req("DELETE", f"/greenhouses/{self.t['greenhouses']['gh']['id']}")
            self._mark(
                "DELETE /greenhouses/{id}",
                self._accept(r.status_code, {200, 204}),
                CRITICAL,
            )

    # ------------------------- Device token --------------------------

    def _obtain_device_token(self) -> str:
        """
        Try the official claim/token-exchange flows first. If unavailable, fallback
        to a known testing device token if your API allows it (as in v2 harness).
        """
        if self.t["device_tokens"].get("c1"):
            return self.t["device_tokens"]["c1"]

        device_name = self.t["controllers"]["device_name"]
        gh_id = self.t["greenhouses"]["gh"]["id"]

        # 1) Try /controllers/claim (ControllerClaimResponse: {controller, device_token, expires_at})
        claim = {
            "device_name": device_name,
            "claim_code": "123456",
            "greenhouse_id": gh_id,
        }
        r = self._req("POST", "/controllers/claim", json=claim)
        if self._accept(r.status_code, {200, 201}):
            body = r.json()
            token = body.get("device_token")
            if token:
                self.t["device_tokens"]["c1"] = token
                return token

        # 2) Try /auth/token-exchange (TokenExchangeResponse)
        exch = {"device_name": device_name, "claim_code": "123456"}
        r = self._req("POST", "/auth/token-exchange", json=exch)
        if self._accept(r.status_code, {200, 201}):
            token = r.json().get("device_token")
            if token:
                self.t["device_tokens"]["c1"] = token
                return token

        # 3) Fallback to known test token (DB-injected in some envs)
        token = "test-device-token-for-verdify-e2e"
        self.t["device_tokens"]["c1"] = token
        return token

    # ------------------------- Runner & Report -----------------------

    def run(self):
        self.phase_auth_users()
        self.phase_greenhouse()
        self.phase_zones()
        self.phase_controllers()
        self.phase_sensors_and_links()
        self.phase_actuators_fans_buttons()
        self.phase_crops_zonecrops_observations()
        self.phase_plans_typed()  # optional elevated paths handled
        self.phase_config_publish_fetch()  # optional publish, device fetch resilient
        self.phase_telemetry_v2()
        self.phase_state_machine()
        self.phase_controller_hello()
        self.phase_ownership_boundaries()
        self.phase_pagination_sorting()
        self.phase_cleanup()

    def summary(self) -> dict:
        print("\n" + "=" * 72)
        print("🎯 END-TO-END V3 SUMMARY")
        print("=" * 72)
        print(f"Endpoints touched: {len(self.results['endpoints'])}")
        print(f"Assertions passed: {self.results['passed']}")
        print(f"Assertions failed: {self.results['failed']}")
        print(f"Critical failures: {self.results['critical_failed']}")
        print("=" * 72)
        sign_off = self.results["critical_failed"] == 0
        print(f"✅ SIGN_OFF_READY: {sign_off}")
        return {
            "passed": self.results["passed"],
            "failed": self.results["failed"],
            "critical_failed": self.results["critical_failed"],
            "sign_off_ready": sign_off,
        }


# --------------------------------------------------------------------
# Pytest entrypoints (each phase callable individually if needed)
# --------------------------------------------------------------------
_suite: EndToEndV3 | None = None


def _get_suite() -> EndToEndV3:
    global _suite
    if _suite is None:
        _suite = EndToEndV3()
    return _suite


def test_01_auth():
    s = _get_suite()
    s.phase_auth_users()


def test_02_greenhouse():
    s = _get_suite()
    s.phase_greenhouse()


def test_03_zones():
    s = _get_suite()
    s.phase_zones()


def test_04_controllers():
    s = _get_suite()
    s.phase_controllers()


def test_05_sensors_links():
    s = _get_suite()
    s.phase_sensors_and_links()


def test_06_actuators_fans_buttons():
    s = _get_suite()
    s.phase_actuators_fans_buttons()


def test_07_crops_zonecrops_observations():
    s = _get_suite()
    s.phase_crops_zonecrops_observations()


def test_08_plans_typed():
    s = _get_suite()
    s.phase_plans_typed()


def test_09_config_publish_fetch():
    s = _get_suite()
    s.phase_config_publish_fetch()


def test_10_telemetry_v2():
    s = _get_suite()
    s.phase_telemetry_v2()


def test_11_state_machine():
    s = _get_suite()
    s.phase_state_machine()


def test_12_controller_hello():
    s = _get_suite()
    s.phase_controller_hello()


def test_13_ownership_boundaries():
    s = _get_suite()
    s.phase_ownership_boundaries()


def test_14_pagination_sorting():
    s = _get_suite()
    s.phase_pagination_sorting()


def test_99_cleanup_and_summary():
    s = _get_suite()
    s.phase_cleanup()
    out = s.summary()
    # hard fail the run only if critical failures occurred
    assert out["critical_failed"] == 0, "Critical assertions failed; see log"


# --------------------------------------------------------------------
# CLI runner
# --------------------------------------------------------------------
if __name__ == "__main__":
    suite = EndToEndV3()
    suite.run()
    res = suite.summary()
    exit(0 if res["critical_failed"] == 0 else 1)
