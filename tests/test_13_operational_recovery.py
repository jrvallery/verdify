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
from pathlib import Path

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
    assert "_PUSH_ECHO_SUPPRESS_S = 300" in src
    assert "_time.time() - pushed_at < _PUSH_ECHO_SUPPRESS_S" in src
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

    pushed = asyncio.run(esp32_push.push_to_esp32([("set_temp_low__f", 64.0, "number")]))

    assert pushed == 1
    assert "temp_low" in shared.recently_pushed


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
