"""Canonical tunable parameter names derived from the tunable registry.

`tunable_registry.py` is the source of truth for every planner, dispatcher,
firmware setpoint, and cfg readback contract. This module keeps the legacy
`ALL_TUNABLES` / `NUMERIC_TUNABLES` / `SWITCH_TUNABLES` API used by Pydantic
models, but no longer carries a second hand-maintained parameter list.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator

from .tunable_registry import REGISTRY

NUMERIC_TUNABLES: frozenset[str] = frozenset(
    name for name, spec in REGISTRY.items() if spec.kind in {"numeric", "enum"}
)
SWITCH_TUNABLES: frozenset[str] = frozenset(name for name, spec in REGISTRY.items() if spec.kind == "switch")
ALL_TUNABLES: frozenset[str] = NUMERIC_TUNABLES | SWITCH_TUNABLES


def _validate_tunable(v: str) -> str:
    if v not in ALL_TUNABLES:
        raise ValueError(
            f"Unknown tunable parameter: {v!r}. Add it to verdify_schemas/tunable_registry.py "
            "if this is a new planner/dispatcher/firmware parameter."
        )
    return v


TunableParameter = Annotated[str, AfterValidator(_validate_tunable)]
