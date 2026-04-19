"""verdify_schemas — shared Pydantic contracts.

The database is the source of truth; every other layer (MCP tools, ingestor
tasks, ESP32 readback, vault writers, website renderer) validates through
these schemas so malformed data fails at the boundary instead of
partial-writing.
"""

from .daily import DailySummaryRow
from .forecast import ForecastHour
from .plan import (
    Conditions,
    ParamRationale,
    Plan,
    PlanEvaluation,
    PlanHypothesisStructured,
    PlanId,
    PlanSource,
    PlanTransition,
    StressWindow,
)
from .setpoint import SetpointChange, SetpointSource
from .tunables import ALL_TUNABLES, NUMERIC_TUNABLES, SWITCH_TUNABLES, TunableParameter

__all__ = [
    "ALL_TUNABLES",
    "Conditions",
    "DailySummaryRow",
    "ForecastHour",
    "NUMERIC_TUNABLES",
    "ParamRationale",
    "Plan",
    "PlanEvaluation",
    "PlanHypothesisStructured",
    "PlanId",
    "PlanSource",
    "PlanTransition",
    "SWITCH_TUNABLES",
    "SetpointChange",
    "SetpointSource",
    "StressWindow",
    "TunableParameter",
]
