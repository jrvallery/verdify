"""Drift guards for typed alert detail payloads."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from verdify_schemas.alerts import (
    ALERT_ENVELOPE_ADAPTER,
    ALERT_TYPES,
    AlertEnvelope,
    BandFnNullAlert,
    ESP32PushFailedAlert,
    ESP32RebootAlert,
    FirmwareReliefCeilingAlert,
    FirmwareVentLatchedAlert,
    FirmwareVersionMismatchAlert,
    HeapPressureCriticalAlert,
    HeapPressureWarningAlert,
    HeatManualOverrideAlert,
    HeatStagingInversionAlert,
    LeakDetectedAlert,
    PlanContextFailedAlert,
    PlannerBandOwnershipDriftAlert,
    PlannerGatewayDeliveryFailedAlert,
    PlannerRequiredPlanMissedAlert,
    PlannerStaleAlert,
    RelayStuckAlert,
    SafetyInvalidAlert,
    SensorOfflineAlert,
    SetpointUnconfirmedAlert,
    SoilSensorOfflineAlert,
    TempSafetyAlert,
    TunableZeroVarianceAlert,
    VpdExtremeAlert,
    VpdStressAlert,
)

NOW = "2026-05-01T12:00:00+00:00"

CASES = {
    "band_fn_null": (
        BandFnNullAlert,
        {"band_row_null": True, "zone_row_null": False},
    ),
    "esp32_push_failed": (
        ESP32PushFailedAlert,
        {"error": "timeout", "change_count": 3},
    ),
    "esp32_reboot": (
        ESP32RebootAlert,
        {"uptime_s": 42.0, "reset_reason": "poweron"},
    ),
    "firmware_relief_ceiling": (
        FirmwareReliefCeilingAlert,
        {"relief_cycle_count": 3, "ceiling_default": 3},
    ),
    "firmware_vent_latched": (
        FirmwareVentLatchedAlert,
        {"vent_latch_timer_s": 1200},
    ),
    "firmware_version_mismatch": (
        FirmwareVersionMismatchAlert,
        {
            "expected_firmware_version": "2026.4.27.2040.c1a6403",
            "live_firmware_version": "2026.4.27.2009.2b5f2a5",
            "diagnostics_ts": NOW,
            "pin_source": "state/expected-firmware-version",
        },
    ),
    "heap_pressure_critical": (
        HeapPressureCriticalAlert,
        {
            "equipment": "heap_pressure_critical",
            "equipment_ts": NOW,
            "last_true_ts": NOW,
            "heap_free_kb": 12.5,
            "heap_diag_ts": NOW,
            "critical_logs_30m": 1,
            "healthy_heap_samples_after_event": 0,
            "last_critical_log_ts": NOW,
            "last_critical_log_message": "Heap pressure CRITICAL",
        },
    ),
    "heap_pressure_warning": (
        HeapPressureWarningAlert,
        {
            "equipment": "heap_pressure_warning",
            "equipment_ts": NOW,
            "last_true_ts": NOW,
            "heap_free_kb": 28.5,
            "heap_diag_ts": NOW,
            "warning_logs_30m": 1,
            "healthy_heap_samples_after_event": 2,
            "last_warning_log_ts": NOW,
            "last_warning_log_message": "Heap pressure WARNING",
        },
    ),
    "heat_manual_override": (
        HeatManualOverrideAlert,
        {"watts": 1200},
    ),
    "heat_staging_inversion": (
        HeatStagingInversionAlert,
        {
            "heat2_on_since": NOW,
            "duration_s": 90.0,
            "temp_avg": 61.2,
            "temp_low": 62.0,
            "d_heat_stage_2": 3.0,
        },
    ),
    "leak_detected": (
        LeakDetectedAlert,
        {"since": NOW},
    ),
    "plan_context_failed": (
        PlanContextFailedAlert,
        {"reason": "timeout", "stderr": "planner context failed", "exit_code": 124},
    ),
    "planner_band_ownership_drift": (
        PlannerBandOwnershipDriftAlert,
        {
            "band_owned_params": ["temp_low", "temp_high", "vpd_low", "vpd_high"],
            "offenders": [{"parameter": "temp_low", "plan_id": "p1", "source": "iris", "rows": 1}],
        },
    ),
    "planner_gateway_delivery_failed": (
        PlannerGatewayDeliveryFailedAlert,
        {
            "failures": [
                {
                    "id": 42,
                    "event_type": "SUNRISE",
                    "event_label": "sunrise",
                    "instance": "opus",
                    "gateway_status": 500,
                    "delivered_at": NOW,
                    "gateway_body": "bad gateway",
                }
            ]
        },
    ),
    "planner_required_plan_missed": (
        PlannerRequiredPlanMissedAlert,
        {
            "misses": [
                {
                    "id": 42,
                    "event_type": "SUNRISE",
                    "event_label": "sunrise",
                    "instance": "opus",
                    "status": "delivery_failed",
                    "gateway_status": 500,
                    "delivered_at": NOW,
                    "gateway_body": "bad gateway",
                }
            ]
        },
    ),
    "planner_stale": (
        PlannerStaleAlert,
        {"age_s": 50_500, "age_h": 14.0},
    ),
    "relay_stuck": (
        RelayStuckAlert,
        {
            "hours_on": 3.5,
            "threshold_hours": 3.0,
            "state_source": "commanded_equipment_state",
            "temp_avg": 72.0,
            "sp_temp_high": 74.0,
            "greenhouse_mode": "HEAT",
            "context_ts": NOW,
        },
    ),
    "safety_invalid": (
        SafetyInvalidAlert,
        {"parameter": "safety_min", "value": 0.0},
    ),
    "sensor_offline": (
        SensorOfflineAlert,
        {"type": "climate", "staleness_ratio": 8.5},
    ),
    "setpoint_unconfirmed": (
        SetpointUnconfirmedAlert,
        {
            "parameter": "vpd_target_south",
            "requested_value": 1.3,
            "last_cfg_readback": 1.2,
            "age_s": 360,
            "pushed_at": NOW,
        },
    ),
    "soil_sensor_offline": (
        SoilSensorOfflineAlert,
        {"column": "soil_moisture_south_1", "sensor": "soil.south_1"},
    ),
    "temp_safety": (
        TempSafetyAlert,
        {"temp_f": 101.5},
    ),
    "tunable_zero_variance": (
        TunableZeroVarianceAlert,
        {"parameter": "vpd_target_west", "sample_count": 33_000, "pinned_value": 1.2},
    ),
    "vpd_extreme": (
        VpdExtremeAlert,
        {"vpd_kpa": 3.2},
    ),
    "vpd_stress": (
        VpdStressAlert,
        {
            "vpd_stress_hours": 2.4,
            "recent_samples": 12,
            "recent_high_samples": 9,
            "recent_high_fraction": 0.75,
            "avg_vpd_15m": 2.4,
            "avg_vpd_high_15m": 1.8,
        },
    ),
}


def _envelope(alert_type: str, details: dict) -> dict:
    return {
        "alert_type": alert_type,
        "severity": "warning",
        "category": "system",
        "message": f"{alert_type} fired",
        "details": details,
    }


@pytest.mark.parametrize("alert_type", ALERT_TYPES)
def test_envelope_dispatches_per_type(alert_type: str):
    expected_cls, details = CASES[alert_type]

    typed = ALERT_ENVELOPE_ADAPTER.validate_python(_envelope(alert_type, details))

    assert isinstance(typed, expected_cls)


@pytest.mark.parametrize("alert_type", ALERT_TYPES)
def test_alert_envelope_keeps_legacy_model_validate_api(alert_type: str):
    _, details = CASES[alert_type]

    env = AlertEnvelope.model_validate(_envelope(alert_type, details))

    assert env.alert_type == alert_type
    assert isinstance(env.details, dict)


@pytest.mark.parametrize("alert_type", ALERT_TYPES)
def test_envelope_rejects_extra_detail_fields(alert_type: str):
    _, details = CASES[alert_type]

    with pytest.raises(ValidationError):
        AlertEnvelope.model_validate(_envelope(alert_type, {**details, "typo_field": "bad"}))


def test_every_alert_type_has_a_case():
    assert set(CASES) == set(ALERT_TYPES)


def test_schema_covers_alert_types_in_write_paths():
    root = Path(__file__).resolve().parents[2]
    sources = [
        root / "ingestor" / "tasks.py",
        root / "ingestor" / "iris_planner.py",
        root / "api" / "main.py",
    ]
    found: set[str] = set()
    patterns = [
        re.compile(r'"alert_type"\s*:\s*"([^"]+)"'),
        re.compile(r"alert_type\s*=\s*'([^']+)'"),
        re.compile(r"VALUES\s*\('([^']+)',\s*'\w+',\s*'\w+'", re.MULTILINE),
    ]
    for source in sources:
        text = source.read_text()
        for pattern in patterns:
            found.update(pattern.findall(text))

    assert found <= set(ALERT_TYPES)
