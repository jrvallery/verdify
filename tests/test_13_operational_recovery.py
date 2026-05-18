"""Operational recovery regression tests.

Covers fixes from ingestor/sprint-25.1:
  - tasks.py must not import the ingestor.py entrypoint for direct ESP32 push
  - ESP32 push echo suppression must use shared process state
  - service modules must not hardcode the coordinator worktree on sys.path
  - active planner params in the live DB must have dispatcher routes
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from verdify_schemas.tunable_registry import CROP_BAND_REG

INGESTOR_PATH = str(Path(__file__).resolve().parent.parent / "ingestor")
if INGESTOR_PATH not in sys.path:
    sys.path.insert(0, INGESTOR_PATH)


def test_tasks_does_not_import_ingestor_entrypoint_for_push():
    """Importing ingestor.py from tasks.py creates split module state under
    systemd because the service entrypoint is __main__."""
    src = Path(INGESTOR_PATH, "tasks.py").read_text()
    assert "from ingestor import push_to_esp32" not in src
    assert "from esp32_push import push_to_esp32" in src


def test_service_modules_use_repo_relative_schema_path():
    for filename in ("ingestor.py", "tasks.py"):
        src = Path(INGESTOR_PATH, filename).read_text()
        assert 'sys.path.insert(0, "/mnt/iris/verdify")' not in src
        assert "Path(__file__).resolve().parent.parent" in src


def test_gap_tracking_uses_disconnect_timestamp():
    src = Path(INGESTOR_PATH, "ingestor.py").read_text()
    assert "last_disconnected_at" in src
    assert "since disconnect" in src
    assert "last_connected_at" not in src


def test_echo_suppression_covers_delayed_esphome_state_publish():
    src = Path(INGESTOR_PATH, "ingestor.py").read_text()
    assert "_PUSH_ECHO_SUPPRESS_S = 900" in src
    assert "_time.time() - pushed_at < _PUSH_ECHO_SUPPRESS_S and _same_pushed_value(param, val)" in src
    assert "RT push suppressed for recently pushed" in src


def test_esp32_push_marks_shared_recently_pushed():
    import esp32_push
    import shared

    class FakeClient:
        def number_command(self, key, val):
            self.last = ("number", key, val)

    shared.esp32["client"] = FakeClient()
    shared.esp32["keys"] = {"set_temp_low__f": 123}
    shared.recently_pushed.clear()
    shared.recently_pushed_values.clear()

    pushed = asyncio.run(esp32_push.push_to_esp32([("set_temp_low__f", 64.0, "number")]))

    assert pushed == 1
    assert "temp_low" in shared.recently_pushed
    assert shared.recently_pushed_values["temp_low"] == 64.0


def test_occupancy_push_targets_presence_state_not_inhibit_tunable():
    import esp32_push
    import shared
    from entity_map import EQUIPMENT_SWITCH_MAP

    class FakeClient:
        def __init__(self):
            self.commands = []

        def switch_command(self, key, state):
            self.commands.append((key, state))

    client = FakeClient()
    shared.esp32["client"] = client
    shared.esp32["keys"] = {"greenhouse_occupied": 456}
    esp32_push._LAST_COMMAND_TS = 0.0

    pushed = asyncio.run(esp32_push.push_occupancy_to_esp32(True, "test"))

    assert pushed == 1
    assert client.commands == [(456, True)]
    assert EQUIPMENT_SWITCH_MAP["greenhouse_occupied"] == "occupancy"


def test_occupancy_quiet_preserves_manual_owner_when_window_covers_refresh():
    import occupancy
    from quiet_mode import QUIET_MODE_ENTITY, QUIET_REASON_ENTITY, QUIET_UNTIL_ENTITY, iso_utc

    class FakeConn:
        def __init__(self):
            self.inserts = []

        async def fetch(self, *args, **kwargs):
            raise AssertionError("manual active quiet should not fetch restore params")

        async def execute(self, _sql, *args):
            self.inserts.append(args)

    conn = FakeConn()
    manual_until = iso_utc(datetime.now(UTC) + timedelta(hours=1))
    state = {
        QUIET_MODE_ENTITY: "on",
        QUIET_UNTIL_ENTITY: manual_until,
        QUIET_REASON_ENTITY: "manual:recording",
    }

    until = asyncio.run(occupancy._enable_occupancy_quiet(conn, state, "test"))

    assert until == manual_until
    assert not any(args[0] == QUIET_REASON_ENTITY for args in conn.inserts)
    assert ("recording_quiet_occupancy_active", "on") in conn.inserts


def test_occupancy_quiet_takes_owner_when_manual_window_would_expire():
    import occupancy
    from quiet_mode import QUIET_MODE_ENTITY, QUIET_REASON_ENTITY, QUIET_UNTIL_ENTITY, iso_utc

    class FakeConn:
        def __init__(self):
            self.inserts = []

        async def fetch(self, *args, **kwargs):
            raise AssertionError("active quiet should not fetch restore params")

        async def execute(self, _sql, *args):
            self.inserts.append(args)

    conn = FakeConn()
    manual_until = iso_utc(datetime.now(UTC) + timedelta(minutes=1))
    state = {
        QUIET_MODE_ENTITY: "on",
        QUIET_UNTIL_ENTITY: manual_until,
        QUIET_REASON_ENTITY: "manual:recording",
    }

    until = asyncio.run(occupancy._enable_occupancy_quiet(conn, state, "test"))

    assert until > manual_until
    assert (QUIET_REASON_ENTITY, "occupancy:test") in conn.inserts
    assert ("recording_quiet_occupancy_active", "on") in conn.inserts


def test_quiet_overlay_band_params_are_not_tagged_as_crop_band():
    import tasks

    assert tasks._dispatch_source("temp_low", {}, {"temp_low"}) == "manual"
    assert tasks._dispatch_source("temp_high", {}, {"temp_high"}) == "manual"
    assert tasks._dispatch_source("vpd_low", {}, {"vpd_low"}) == "manual"
    assert tasks._dispatch_source("vpd_high", {}, {"vpd_high"}) == "manual"
    assert tasks._dispatch_source("temp_low", {}, set()) == "band"
    assert tasks._dispatch_source("mister_all_kpa", {}, {"mister_all_kpa"}) == "manual"


def test_live_active_plan_params_are_pushable():
    """The current planner surface should not contain params the dispatcher
    cannot route to ESP32. This catches schema/firmware/entity-map drift using
    the same live DB-backed style as the rest of the smoke suite."""
    from entity_map import PARAM_TO_ENTITY, SWITCH_TO_ENTITY

    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "verdify-timescaledb",
            "psql",
            "-U",
            "verdify",
            "-d",
            "verdify",
            "-t",
            "-A",
            "-c",
            "COPY (SELECT DISTINCT parameter FROM v_active_plan ORDER BY 1) TO STDOUT",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    active = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    pushable = set(PARAM_TO_ENTITY) | set(SWITCH_TO_ENTITY)

    assert sorted(active - pushable) == []


def test_live_active_plan_has_no_band_owned_rows():
    """Crop-band params are dispatcher-owned context, not planner waypoints.

    Query setpoint_plan directly rather than v_active_plan so stale active rows
    from older plans cannot hide behind a newer clean plan.
    """
    band_sql = ",".join(
        "'" + param.replace("'", "''") + "'"
        for param in sorted(p for p in CROP_BAND_REG if p.startswith("temp_") or p in {"vpd_low", "vpd_high"})
    )
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "verdify-timescaledb",
            "psql",
            "-U",
            "verdify",
            "-d",
            "verdify",
            "-t",
            "-A",
            "-c",
            f"""
            COPY (
                SELECT parameter || ':' || coalesce(plan_id, '<null>') || ':' || coalesce(source, '<null>')
                  FROM setpoint_plan
                 WHERE is_active = true
                   AND parameter IN ({band_sql})
                 ORDER BY 1
            ) TO STDOUT
            """,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    offenders = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    assert offenders == []
