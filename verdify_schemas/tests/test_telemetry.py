"""Telemetry row schema tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from verdify_schemas.telemetry import (
    ClimateRow,
    Diagnostics,
    EnergySample,
    EquipmentStateEvent,
    OverrideEvent,
    SystemStateRow,
)

NOW = datetime(2026, 4, 19, 1, 0, tzinfo=UTC)


class TestClimateRow:
    def test_minimal(self):
        row = ClimateRow(ts=NOW)
        assert row.greenhouse_id == "vallery"
        assert row.temp_avg is None

    def test_full_sensible_row(self):
        row = ClimateRow(
            ts=NOW,
            temp_avg=72.5,
            rh_avg=55.0,
            vpd_avg=0.8,
            dew_point=55.2,
            lux=820.0,
            dli_today=7.2,
            hydro_ph=6.22,
            hydro_ec_us_cm=2480.0,
        )
        assert row.hydro_ph == 6.22

    def test_rejects_out_of_range_rh(self):
        with pytest.raises(ValidationError):
            ClimateRow(ts=NOW, rh_avg=120.0)

    def test_rejects_out_of_range_vpd(self):
        with pytest.raises(ValidationError):
            ClimateRow(ts=NOW, vpd_avg=25.0)

    def test_rejects_negative_flow(self):
        with pytest.raises(ValidationError):
            ClimateRow(ts=NOW, precip_in=-1.0)

    def test_hydroponics_ph_out_of_range(self):
        with pytest.raises(ValidationError):
            ClimateRow(ts=NOW, hydro_ph=15.0)

    def test_tolerates_unknown_columns(self):
        row = ClimateRow.model_validate({"ts": NOW, "some_new_column_added_next_month": 123})
        assert row.ts == NOW


class TestDiagnostics:
    def test_valid(self):
        d = Diagnostics(
            ts=NOW,
            wifi_rssi=-47.0,
            heap_bytes=180000.0,
            uptime_s=3600.0,
            probe_health="4/4 ok",
            reset_reason="Software reset",
            firmware_version="2026.4.18",
            active_probe_count=4,
            relief_cycle_count=0,
            vent_latch_timer_s=0,
        )
        assert d.active_probe_count == 4

    def test_rejects_rssi_above_zero(self):
        with pytest.raises(ValidationError):
            Diagnostics(ts=NOW, wifi_rssi=10.0)

    def test_rejects_probe_count_over_4(self):
        with pytest.raises(ValidationError):
            Diagnostics(ts=NOW, active_probe_count=5)

    def test_rejects_vent_latch_above_1800(self):
        with pytest.raises(ValidationError):
            Diagnostics(ts=NOW, vent_latch_timer_s=5000)


class TestEquipmentStateEvent:
    def test_valid_fan1_on(self):
        ev = EquipmentStateEvent(ts=NOW, equipment="fan1", state=True)
        assert ev.state is True

    def test_valid_misting_off(self):
        ev = EquipmentStateEvent(ts=NOW, equipment="mister_south", state=False)
        assert ev.equipment == "mister_south"


class TestEnergySample:
    def test_valid(self):
        e = EnergySample(ts=NOW, watts_total=450.0, watts_fans=120.0, kwh_today=3.2)
        assert e.kwh_today == 3.2

    def test_negative_kwh_rejected(self):
        with pytest.raises(ValidationError):
            EnergySample(ts=NOW, kwh_today=-5.0)


class TestSystemStateRow:
    def test_valid(self):
        s = SystemStateRow(ts=NOW, entity="greenhouse_state", value="SEALED_MIST")
        assert s.value == "SEALED_MIST"


class TestOverrideEvent:
    def test_valid(self):
        ov = OverrideEvent(
            ts=NOW,
            override_type="occupancy_blocks_moisture,fog_gate_rh",
            mode="IDLE",
            details={"rh": 82.0, "occupancy": True},
        )
        assert ov.details["rh"] == 82.0
