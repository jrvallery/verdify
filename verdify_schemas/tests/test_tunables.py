"""Tunable-parameter schema tests.

Every param the dispatcher can emit must appear in ALL_TUNABLES; every
ALL_TUNABLES entry must have a route in entity_map.SETPOINT_MAP. CI drift
is caught here, not post-hoc in production.
"""

from __future__ import annotations

import sys

import pytest
from pydantic import TypeAdapter, ValidationError

from verdify_schemas.tunables import (
    ALL_TUNABLES,
    NUMERIC_TUNABLES,
    SWITCH_TUNABLES,
    TunableParameter,
)


class TestTunableEnumShape:
    def test_numeric_and_switch_are_disjoint(self):
        assert NUMERIC_TUNABLES.isdisjoint(SWITCH_TUNABLES)

    def test_all_tunables_is_union(self):
        assert ALL_TUNABLES == NUMERIC_TUNABLES | SWITCH_TUNABLES

    def test_every_switch_starts_with_sw(self):
        bad = [t for t in SWITCH_TUNABLES if not t.startswith("sw_")]
        assert not bad, f"Switch tunables must start with 'sw_': {bad}"

    def test_no_numeric_starts_with_sw(self):
        bad = [t for t in NUMERIC_TUNABLES if t.startswith("sw_")]
        assert not bad, f"Numeric tunables must NOT start with 'sw_': {bad}"

    def test_tunable_set_matches_entity_map(self):
        """Drift guard: adding a tunable to entity_map but not here = silent drop."""
        sys.path.insert(0, "/srv/verdify/ingestor")
        from entity_map import SETPOINT_MAP

        em_tunables = set(SETPOINT_MAP.values())
        schema_tunables = set(ALL_TUNABLES)

        missing_in_schema = sorted(em_tunables - schema_tunables)
        missing_in_em = sorted(schema_tunables - em_tunables)

        assert not missing_in_schema, (
            f"entity_map has tunables the schema doesn't know: {missing_in_schema}. Add to verdify_schemas/tunables.py."
        )
        assert not missing_in_em, (
            f"schema has tunables entity_map doesn't route: {missing_in_em}. "
            "Remove from schema or add to entity_map.SETPOINT_MAP."
        )


class TestTunableParameterValidator:
    def test_accepts_known_numeric(self):
        adapter = TypeAdapter(TunableParameter)
        assert adapter.validate_python("temp_low") == "temp_low"

    def test_accepts_known_switch(self):
        adapter = TypeAdapter(TunableParameter)
        assert adapter.validate_python("sw_economiser_enabled") == "sw_economiser_enabled"

    def test_rejects_unknown(self):
        adapter = TypeAdapter(TunableParameter)
        with pytest.raises(ValidationError, match="Unknown tunable parameter"):
            adapter.validate_python("something_fake")

    def test_rejects_case_mismatch(self):
        adapter = TypeAdapter(TunableParameter)
        with pytest.raises(ValidationError):
            adapter.validate_python("TEMP_LOW")
