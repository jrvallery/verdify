"""Drift guards — assert every DB-row schema's fields are a subset of the
live table's `information_schema.columns`. When the DB grows or loses a
column, the matching schema test fires immediately instead of after an
outage downstream.

Each guard:
  - Queries information_schema.columns for the target table's column set
  - Compares against the Pydantic model's field names
  - Allows the schema to be a SUBSET (model.extra="ignore" tolerates extras)
  - Flags fields the schema declares but the DB doesn't have (renamed /
    dropped) — this is the real regression path.

Runs against live Docker Postgres. If `docker` isn't available, these skip
(for example on a CI runner that builds schemas without a DB attached).
"""

from __future__ import annotations

import subprocess

import pytest

from verdify_schemas.alerts import AlertLogRow
from verdify_schemas.crops import Crop, CropEvent, Observation
from verdify_schemas.daily import DailySummaryRow
from verdify_schemas.forecast import ForecastHour
from verdify_schemas.lessons import PlannerLesson
from verdify_schemas.plan import PlanJournalRow
from verdify_schemas.setpoint import (
    SetpointChange,
    SetpointClamp,
    SetpointPlanRow,
    SetpointSnapshot,
)
from verdify_schemas.telemetry import (
    ClimateRow,
    Diagnostics,
    EnergySample,
    EquipmentStateEvent,
    OverrideEvent,
    SystemStateRow,
)


def _docker_available() -> bool:
    r = subprocess.run(["docker", "ps"], capture_output=True, text=True, check=False)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _docker_available(), reason="docker not available")


def _table_columns(table: str) -> set[str]:
    sql = f"SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='{table}'"
    r = subprocess.run(
        ["docker", "exec", "verdify-timescaledb", "psql", "-U", "verdify", "-d", "verdify", "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return {ln.strip() for ln in r.stdout.splitlines() if ln.strip()}


# (schema class, DB table name)
DB_BACKED = [
    (ClimateRow, "climate"),
    (Diagnostics, "diagnostics"),
    (EquipmentStateEvent, "equipment_state"),
    (EnergySample, "energy"),
    (SystemStateRow, "system_state"),
    (OverrideEvent, "override_events"),
    (SetpointChange, "setpoint_changes"),
    (SetpointPlanRow, "setpoint_plan"),
    (SetpointSnapshot, "setpoint_snapshot"),
    (SetpointClamp, "setpoint_clamps"),
    (PlanJournalRow, "plan_journal"),
    (DailySummaryRow, "daily_summary"),
    (ForecastHour, "weather_forecast"),
    (AlertLogRow, "alert_log"),
    (Crop, "crops"),
    (CropEvent, "crop_events"),
    (Observation, "observations"),
    (PlannerLesson, "planner_lessons"),
]


@pytest.mark.parametrize("model_class,table_name", DB_BACKED)
def test_schema_fields_subset_of_db_columns(model_class, table_name):
    """Every field declared in the schema must exist in the DB table."""
    db_cols = _table_columns(table_name)
    if not db_cols:
        pytest.skip(f"table {table_name!r} not found (migration pending?)")
    schema_fields = set(model_class.model_fields.keys())
    missing_in_db = sorted(schema_fields - db_cols)
    assert not missing_in_db, (
        f"{model_class.__name__} declares field(s) the {table_name!r} table doesn't have: "
        f"{missing_in_db}. Either the schema is stale (field renamed/removed in DB) "
        f"or a migration is missing."
    )
