"""Tunable registry — Phase-1 single source of truth for every tunable.

Consolidates what used to live in four separate places that drifted:
- `verdify_schemas.tunables.ALL_TUNABLES` (canonical schema enum)
- `mcp.server.TIER1` (hand-maintained planner allowlist)
- `ingestor.entity_map.SETPOINT_MAP` (dispatcher route)
- `ingestor.entity_map.CFG_READBACK_MAP` (firmware readback)
- `firmware/greenhouse/controls.yaml` clamp pairs

Each new tunable previously required 4 updates kept in sync by hand. Sprint-15
and sprint-15.1 each hit this as the drift cause of planner-rejected pushes
("not a Tier 1 tunable"). This registry is the single definition; TIER1 +
SETPOINT_MAP + CFG_READBACK_MAP become computed views.

Phase 1b.2 (this commit): registry expanded from 13 seed entries to 80 entries
covering every SETPOINT_MAP entry except 14 slated for deletion:
  - grow-light tunables (gl_dli_target, gl_lux_threshold, gl_sunrise_hour,
    gl_sunset_hour, sw_gl_auto_mode) — removed in Phase 1d
  - VPD boost irrigation (irrig_vpd_boost_pct, irrig_vpd_boost_threshold_hrs)
  - legacy mister duty-cycle globals (mister_on_s, mister_off_s,
    mister_all_on_s, mister_all_off_s, mister_max_runtime_min) — superseded
    by mister_pulse_* model
  - fog time-window (fog_time_window_start, fog_time_window_end)

Phase 1c adds cfg_* readbacks for the last fire-and-forget tunables; Phase 1d
retires the legacy tunables.py layer so ALL_TUNABLES derives from here.

Three readback-only params (fallback_window_s, outdoor_temp_f,
outdoor_dewpoint_f) are present in CFG_READBACK_MAP but have no SETPOINT_MAP
route and thus no esp_object_id. They can't be registered until `esp_object_id`
becomes Optional (Phase 1c schema change, out of scope here).

See the rewrite plan at
`.claude-agents/iris-dev/plans/yo-iris-dev-you-help-humming-stonebraker.md`
for the full roadmap.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TunableDef(BaseModel):
    """One row in the tunable registry. Each field has exactly one owner.

    Attributes:
        name: canonical name (snake_case). Matches entry_map.SETPOINT_MAP value.
        kind: numeric (float/int) or switch (bool) or enum (int mapped to symbolic).
        min, max: schema-level bounds (advisory for planner UI). None if unbounded.
        default: firmware default from `greenhouse_types.h::default_setpoints()`.
        fw_clamp_lo, fw_clamp_hi: dispatcher + firmware clamp. Must match the
            `cf(val, lo, hi)` / `ci((int)val, lo, hi)` call in controls.yaml
            `/setpoints` handler. Drift guard checks this every CI run.
        esp_object_id: ESPHome entity object_id (slug). Same string as
            SETPOINT_MAP key today; mcp/ingestor will derive from here.
        cfg_readback_object_id: `cfg_*` sensor slug, if firmware publishes one.
            None ⇒ fire-and-forget; must document rationale in `notes`.
        push_owner: who is the source of truth.
        planner_pushable: can Iris push it via `set_tunable`?
        tier: 1 ⇒ appears in `_PLANNER_CORE` prompt; 2 ⇒ escape-hatch only.
        enum_values: for `kind == "enum"`, int value ↔ symbolic name.
        notes: anything human.
    """

    name: str
    kind: Literal["numeric", "switch", "enum"]
    min: float | None = None
    max: float | None = None
    default: float
    fw_clamp_lo: float | None = None
    fw_clamp_hi: float | None = None
    esp_object_id: str
    cfg_readback_object_id: str | None = None
    push_owner: Literal["planner", "band", "safety", "operator", "dispatcher_default", "firmware_internal"]
    planner_pushable: bool = True
    tier: Literal[1, 2] = 1
    enum_values: dict[str, int] | None = None
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRY — Phase 1b.2 complete. 80 entries covering every SETPOINT_MAP entry
# except the 14 slated for deletion. Entries are grouped by functional area.
#
# Tier assignment rule: tier=1 is the planner's core knob set (must match MCP
# TIER1 to satisfy test_registry_tier1_is_subset_of_mcp_tier1). Everything
# else (crop-band pushes, operator toggles, safety rails, irrigation schedule
# knobs) is tier=2 — the planner CAN push via set_tunable but normally won't.
# ─────────────────────────────────────────────────────────────────────────────

REGISTRY: dict[str, TunableDef] = {
    # ─────────────────────────────────────────────────────────────────────
    # Crop band (push_owner="band"). Dispatcher pushes every planner cycle
    # from the active crop profile. Planner only pushes these when it wants
    # a transient override; tier=2 so the mcp TIER1 subset test stays happy.
    # ─────────────────────────────────────────────────────────────────────
    "temp_low": TunableDef(
        name="temp_low",
        kind="numeric",
        min=30.0,
        max=80.0,
        default=40.0,
        fw_clamp_lo=30.0,
        fw_clamp_hi=80.0,
        esp_object_id="set_temp_low__f",
        cfg_readback_object_id="cfg___temp_low___f_",
        push_owner="band",
        planner_pushable=True,
        tier=2,
        notes="Crop band — dispatcher pushes every cycle. Firmware default wide (40) so safety rails govern if dispatcher silent.",
    ),
    "temp_high": TunableDef(
        name="temp_high",
        kind="numeric",
        min=40.0,
        max=100.0,
        default=95.0,
        fw_clamp_lo=40.0,
        fw_clamp_hi=100.0,
        esp_object_id="set_temp_high__f",
        cfg_readback_object_id="cfg___temp_high___f_",
        push_owner="band",
        planner_pushable=True,
        tier=2,
        notes="Crop band — dispatcher pushes every cycle.",
    ),
    "d_heat_stage_2": TunableDef(
        name="d_heat_stage_2",
        kind="numeric",
        min=2.0,
        max=15.0,
        default=5.0,
        fw_clamp_lo=2.0,
        fw_clamp_hi=15.0,
        esp_object_id="__heat_stage_2__f",
        cfg_readback_object_id="cfg_____heat_s2___f_",
        push_owner="band",
        planner_pushable=True,
        tier=1,
        notes="Forecast-tuned heating aggressiveness. In v2, °F below the interior heating target "
        "(temp_low + 25% band + bias_heat) where heat stage 2 latches.",
    ),
    "d_cool_stage_2": TunableDef(
        name="d_cool_stage_2",
        kind="numeric",
        min=2.0,
        max=15.0,
        default=3.0,
        fw_clamp_lo=2.0,
        fw_clamp_hi=15.0,
        esp_object_id="__cool_stage_2__f",
        cfg_readback_object_id="cfg_____cool_s2___f_",
        push_owner="band",
        planner_pushable=True,
        tier=1,
        notes="°F above temp_high at which fan-2 engages. In MCP TIER1 — planner tunes during summer heat.",
    ),
    "temp_hysteresis": TunableDef(
        name="temp_hysteresis",
        kind="numeric",
        min=0.5,
        max=3.0,
        default=1.5,
        fw_clamp_lo=0.5,
        fw_clamp_hi=3.0,
        esp_object_id="temp_hysteresis__f",
        cfg_readback_object_id="cfg___temp_hyst___f_",
        push_owner="band",
        planner_pushable=True,
        tier=1,
        notes="Forecast-tuned temperature transition hysteresis. Wider values reduce mode churn; narrower values tighten band tracking.",
    ),
    "heat_hysteresis": TunableDef(
        name="heat_hysteresis",
        kind="numeric",
        min=0.0,
        max=3.0,
        default=1.0,
        fw_clamp_lo=0.0,
        fw_clamp_hi=3.0,
        esp_object_id="heat_hysteresis__f",
        cfg_readback_object_id="cfg___heat_hyst___f_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Forecast-tuned heat-stage clear margin above the interior heating target. Higher values hold heat longer.",
    ),
    "vpd_low": TunableDef(
        name="vpd_low",
        kind="numeric",
        min=0.1,
        max=1.0,
        default=0.35,
        fw_clamp_lo=0.1,
        fw_clamp_hi=1.0,
        esp_object_id="set_vpd_low_kpa",
        cfg_readback_object_id="cfg___vpd_low__kpa_",
        push_owner="band",
        planner_pushable=True,
        tier=2,
        notes="Crop band low-VPD threshold. Dispatcher pushes every cycle.",
    ),
    "vpd_high": TunableDef(
        name="vpd_high",
        kind="numeric",
        min=0.4,
        max=3.0,
        default=2.80,
        fw_clamp_lo=0.4,
        fw_clamp_hi=3.0,
        esp_object_id="set_vpd_high_kpa",
        cfg_readback_object_id="cfg___vpd_high__kpa_",
        push_owner="band",
        planner_pushable=True,
        tier=2,
        notes="Crop band high-VPD threshold; firmware seal entry trigger.",
    ),
    "vpd_hysteresis": TunableDef(
        name="vpd_hysteresis",
        kind="numeric",
        min=0.05,
        max=0.5,
        default=0.30,
        fw_clamp_lo=0.05,
        fw_clamp_hi=0.5,
        esp_object_id="vpd_hysteresis_kpa",
        cfg_readback_object_id="cfg___vpd_hyst__kpa_",
        push_owner="band",
        planner_pushable=True,
        tier=1,
        notes="In MCP TIER1 — planner tunes to widen/tighten seal exit during humid regimes.",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Safety rails (push_owner="safety"). Operator-only. Planner cannot push
    # these (planner_pushable=False) — drift guard will keep MCP from
    # accidentally exposing them via set_tunable.
    # ─────────────────────────────────────────────────────────────────────
    "safety_min": TunableDef(
        name="safety_min",
        kind="numeric",
        min=30.0,
        max=60.0,
        default=45.0,
        fw_clamp_lo=30.0,
        fw_clamp_hi=60.0,
        esp_object_id="safety_min__f",
        cfg_readback_object_id="cfg___safety_min___f_",
        push_owner="safety",
        planner_pushable=False,
        tier=2,
        notes="Hard cold rail — SAFETY_HEAT mode trigger. Operator-only.",
    ),
    "safety_max": TunableDef(
        name="safety_max",
        kind="numeric",
        min=80.0,
        max=110.0,
        default=95.0,
        fw_clamp_lo=80.0,
        fw_clamp_hi=110.0,
        esp_object_id="safety_max__f",
        cfg_readback_object_id="cfg___safety_max___f_",
        push_owner="safety",
        planner_pushable=False,
        tier=2,
        notes="Hard hot rail — SAFETY_COOL mode trigger. Operator-only.",
    ),
    "safety_vpd_min": TunableDef(
        name="safety_vpd_min",
        kind="numeric",
        min=0.1,
        max=1.5,
        default=0.30,
        fw_clamp_lo=0.1,
        fw_clamp_hi=1.5,
        esp_object_id="safety_vpd_min_kpa",
        cfg_readback_object_id="cfg___safety_vpd_min__kpa_",
        push_owner="safety",
        planner_pushable=False,
        tier=2,
        notes="Hard low-VPD rail (vpd_min_safe). Operator-only.",
    ),
    "safety_vpd_max": TunableDef(
        name="safety_vpd_max",
        kind="numeric",
        min=2.5,
        max=3.0,
        default=2.50,
        fw_clamp_lo=2.5,
        fw_clamp_hi=3.0,
        esp_object_id="safety_vpd_max_kpa",
        cfg_readback_object_id="cfg___safety_vpd_max__kpa_",
        push_owner="safety",
        planner_pushable=False,
        tier=2,
        notes="Hard high-VPD rail (vpd_max_safe). Operator-only.",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Mister engage thresholds + delays (push_owner="planner", tier=1).
    # ─────────────────────────────────────────────────────────────────────
    "mister_engage_kpa": TunableDef(
        name="mister_engage_kpa",
        kind="numeric",
        min=0.5,
        max=2.5,
        default=1.6,
        fw_clamp_lo=0.5,
        fw_clamp_hi=2.5,
        esp_object_id="vpd_mister_engage_kpa",
        cfg_readback_object_id="cfg_mister_engage__kpa_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="VPD threshold to engage first mister zone.",
    ),
    "mister_all_kpa": TunableDef(
        name="mister_all_kpa",
        kind="numeric",
        min=1.0,
        max=2.5,
        default=1.9,
        fw_clamp_lo=1.0,
        fw_clamp_hi=2.5,
        esp_object_id="vpd_mister_all_kpa",
        cfg_readback_object_id="cfg_mister_all__kpa_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="VPD threshold to engage all mister zones (escalation).",
    ),
    "mister_engage_delay_s": TunableDef(
        name="mister_engage_delay_s",
        kind="numeric",
        min=30,
        max=900,
        default=45,
        fw_clamp_lo=30,
        fw_clamp_hi=900,
        esp_object_id="mister_engage_delay__s_",
        cfg_readback_object_id=None,
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Delay before first v2 mister pulse during a sealed or vent-assist moisture cycle.",
    ),
    "mister_all_delay_s": TunableDef(
        name="mister_all_delay_s",
        kind="numeric",
        min=60,
        max=900,
        default=300,
        fw_clamp_lo=60,
        fw_clamp_hi=900,
        esp_object_id="mister_all_delay__s_",
        cfg_readback_object_id=None,
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Legacy duty-cycle delay. Phase 1c may add cfg_* readback.",
    ),
    "mister_water_budget_gal": TunableDef(
        name="mister_water_budget_gal",
        kind="numeric",
        min=100,
        max=600,
        default=500.0,
        fw_clamp_lo=100,
        fw_clamp_hi=600,
        esp_object_id="mister_water_budget__gal_",
        cfg_readback_object_id="cfg___mister_water_budget__gal_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Daily mister water cap. In MCP TIER1 — planner trims on drought regimes.",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Mister pulse-rotation model (tier=1). Phase-1c added cfg_* readbacks.
    # ─────────────────────────────────────────────────────────────────────
    "mister_pulse_on_s": TunableDef(
        name="mister_pulse_on_s",
        kind="numeric",
        min=30,
        max=90,
        default=60,
        fw_clamp_lo=30,
        fw_clamp_hi=90,
        esp_object_id="mister_pulse_on__s_",
        cfg_readback_object_id="cfg___mister_pulse_on__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Pulse-rotation ON duration per zone.",
    ),
    "mister_pulse_gap_s": TunableDef(
        name="mister_pulse_gap_s",
        kind="numeric",
        min=10,
        max=60,
        default=45,
        fw_clamp_lo=10,
        fw_clamp_hi=60,
        esp_object_id="mister_pulse_gap__s_",
        cfg_readback_object_id="cfg___mister_pulse_gap__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Pulse-rotation OFF (evap dwell) between zones.",
    ),
    "mister_vpd_weight": TunableDef(
        name="mister_vpd_weight",
        kind="numeric",
        min=0.5,
        max=5.0,
        default=1.5,
        fw_clamp_lo=0.5,
        fw_clamp_hi=5.0,
        esp_object_id="mister_vpd_weight",
        cfg_readback_object_id="cfg___mister_vpd_weight",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Weight on VPD gap in zone-selection scoring formula.",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Per-zone VPD targets (push_owner="band" — dispatcher pushes from crop
    # profile) + related scoring tunables. Tier=2: planner rarely overrides.
    # ─────────────────────────────────────────────────────────────────────
    "vpd_target_south": TunableDef(
        name="vpd_target_south",
        kind="numeric",
        min=0.3,
        max=3.0,
        default=1.3,
        fw_clamp_lo=0.3,
        fw_clamp_hi=3.0,
        esp_object_id="vpd_target_south__kpa_",
        cfg_readback_object_id="cfg___vpd_target_south__kpa_",
        push_owner="band",
        planner_pushable=True,
        tier=2,
        notes="Per-zone VPD target — dispatcher pushes from crop band.",
    ),
    "vpd_target_west": TunableDef(
        name="vpd_target_west",
        kind="numeric",
        min=0.3,
        max=3.0,
        default=1.2,
        fw_clamp_lo=0.3,
        fw_clamp_hi=3.0,
        esp_object_id="vpd_target_west__kpa_",
        cfg_readback_object_id="cfg___vpd_target_west__kpa_",
        push_owner="band",
        planner_pushable=True,
        tier=2,
    ),
    "vpd_target_east": TunableDef(
        name="vpd_target_east",
        kind="numeric",
        min=0.3,
        max=3.0,
        default=1.0,
        fw_clamp_lo=0.3,
        fw_clamp_hi=3.0,
        esp_object_id="vpd_target_east__kpa_",
        cfg_readback_object_id="cfg___vpd_target_east__kpa_",
        push_owner="band",
        planner_pushable=True,
        tier=2,
    ),
    "vpd_target_center": TunableDef(
        name="vpd_target_center",
        kind="numeric",
        min=0.1,
        max=3.0,
        default=0.8,
        fw_clamp_lo=0.1,
        fw_clamp_hi=3.0,
        esp_object_id="vpd_target_center__kpa_",
        cfg_readback_object_id="cfg___vpd_target_center__kpa_",
        push_owner="band",
        planner_pushable=True,
        tier=2,
        notes="Center zone has wider floor (0.1) to tolerate seedling propagation.",
    ),
    "mister_center_penalty": TunableDef(
        name="mister_center_penalty",
        kind="numeric",
        min=0.0,
        max=1.0,
        default=0.5,
        fw_clamp_lo=0.0,
        fw_clamp_hi=1.0,
        esp_object_id="mister_center_penalty",
        cfg_readback_object_id="cfg___mister_center_penalty",
        push_owner="planner",
        planner_pushable=True,
        tier=2,
        notes="Score penalty on center zone to discourage over-misting seedlings.",
    ),
    "east_adjacency_factor": TunableDef(
        name="east_adjacency_factor",
        kind="numeric",
        min=0.0,
        max=1.0,
        default=0.3,
        fw_clamp_lo=0.0,
        fw_clamp_hi=1.0,
        esp_object_id="east_adjacency_factor",
        cfg_readback_object_id="cfg___east_adjacency_factor",
        push_owner="planner",
        planner_pushable=True,
        tier=2,
        notes="Weight for borrowing east-zone signal into adjacent scoring (no east mister).",
    ),
    "min_fog_on_s": TunableDef(
        name="min_fog_on_s",
        kind="numeric",
        min=15,
        max=300,
        default=60,
        fw_clamp_lo=15,
        fw_clamp_hi=300,
        esp_object_id="min_fog_on__s_",
        cfg_readback_object_id=None,
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Fog minimum ON time — in MCP TIER1.",
    ),
    "min_fog_off_s": TunableDef(
        name="min_fog_off_s",
        kind="numeric",
        min=15,
        max=300,
        default=60,
        fw_clamp_lo=15,
        fw_clamp_hi=300,
        esp_object_id="min_fog_off__s_",
        cfg_readback_object_id=None,
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Fog minimum OFF time — in MCP TIER1.",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Equipment timing (heaters/fans/vent/bursts).
    # ─────────────────────────────────────────────────────────────────────
    "min_heat_on_s": TunableDef(
        name="min_heat_on_s",
        kind="numeric",
        min=30,
        max=300,
        default=120,
        fw_clamp_lo=30,
        fw_clamp_hi=300,
        esp_object_id="min_heat_on__s_",
        cfg_readback_object_id="cfg___min_heat_on__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Heater min-on dwell. In MCP TIER1.",
    ),
    "min_fan_on_s": TunableDef(
        name="min_fan_on_s",
        kind="numeric",
        min=30,
        max=300,
        default=120,
        fw_clamp_lo=30,
        fw_clamp_hi=300,
        esp_object_id="min_fan_on__s_",
        cfg_readback_object_id="cfg___min_fan_on__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=2,
        notes="Fan min-on dwell. Rarely tuned by planner.",
    ),
    "min_fan_off_s": TunableDef(
        name="min_fan_off_s",
        kind="numeric",
        min=30,
        max=300,
        default=90,
        fw_clamp_lo=30,
        fw_clamp_hi=300,
        esp_object_id="min_fan_off__s_",
        cfg_readback_object_id="cfg___min_fan_off__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=2,
    ),
    "min_vent_on_s": TunableDef(
        name="min_vent_on_s",
        kind="numeric",
        min=10,
        max=300,
        default=60,
        fw_clamp_lo=10,
        fw_clamp_hi=300,
        esp_object_id="min_vent_on__s_",
        cfg_readback_object_id="cfg___min_vent_on__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Vent min-on dwell. In MCP TIER1.",
    ),
    "min_vent_off_s": TunableDef(
        name="min_vent_off_s",
        kind="numeric",
        min=10,
        max=300,
        default=60,
        fw_clamp_lo=10,
        fw_clamp_hi=300,
        esp_object_id="min_vent_off__s_",
        cfg_readback_object_id="cfg___min_vent_off__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Vent min-off dwell. In MCP TIER1.",
    ),
    "lead_rotate_s": TunableDef(
        name="lead_rotate_s",
        kind="numeric",
        min=60,
        max=1800,
        default=600,
        fw_clamp_lo=60,
        fw_clamp_hi=1800,
        esp_object_id="lead_rotate__s_",
        cfg_readback_object_id="cfg___lead_rotate_timeout__s_",
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Lead/lag fan rotation timer. Operator-tuned.",
    ),
    "fan_burst_min": TunableDef(
        name="fan_burst_min",
        kind="numeric",
        min=1,
        max=60,
        default=10,
        fw_clamp_lo=1,
        fw_clamp_hi=60,
        esp_object_id="fan_burst__min_",
        cfg_readback_object_id="cfg___fan_burst__min_",
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Manual fan-burst duration (HA button).",
    ),
    "vent_bypass_min": TunableDef(
        name="vent_bypass_min",
        kind="numeric",
        min=1,
        max=60,
        default=10,
        fw_clamp_lo=1,
        fw_clamp_hi=60,
        esp_object_id="vent_bypass__min_",
        cfg_readback_object_id="cfg___vent_bypass__min_",
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Manual vent-bypass duration (HA button).",
    ),
    "fog_burst_min": TunableDef(
        name="fog_burst_min",
        kind="numeric",
        min=1,
        max=60,
        default=10,
        fw_clamp_lo=1,
        fw_clamp_hi=60,
        esp_object_id="fog_burst__min_",
        cfg_readback_object_id="cfg___fog_burst__min_",
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Manual fog-burst duration (HA button).",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Fog safety gates. Tier=2 — operator rarely tunes.
    # ─────────────────────────────────────────────────────────────────────
    "fog_rh_ceiling_pct": TunableDef(
        name="fog_rh_ceiling_pct",
        kind="numeric",
        min=75,
        max=98,
        default=90,
        fw_clamp_lo=75,
        fw_clamp_hi=98,
        esp_object_id="fog_rh_ceiling____",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Fog blocks when indoor RH exceeds this. Safety-adjacent.",
    ),
    "fog_min_temp_f": TunableDef(
        name="fog_min_temp_f",
        kind="numeric",
        min=40,
        max=65,
        default=55,
        fw_clamp_lo=40,
        fw_clamp_hi=65,
        esp_object_id="fog_min_temp__f_",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Fog blocks when indoor temp below this (evap cooling hurts in cold).",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # VPD-primary state machine dwell / lead / reopen (MCP TIER1 core).
    # ─────────────────────────────────────────────────────────────────────
    "vpd_watch_dwell_s": TunableDef(
        name="vpd_watch_dwell_s",
        kind="numeric",
        min=15,
        max=120,
        default=60,
        fw_clamp_lo=15,
        fw_clamp_hi=120,
        esp_object_id="vpd_watch_dwell__s_",
        cfg_readback_object_id="cfg___vpd_watch_dwell__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="VPD_WATCH observation window before engaging mist.",
    ),
    "mist_vent_close_lead_s": TunableDef(
        name="mist_vent_close_lead_s",
        kind="numeric",
        min=0,
        max=60,
        default=15,
        fw_clamp_lo=0,
        fw_clamp_hi=60,
        esp_object_id="mist_vent_close_lead__s_",
        cfg_readback_object_id="cfg___mist_vent_close_lead__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Lead time for vent close before mist engages.",
    ),
    "mist_max_closed_vent_s": TunableDef(
        name="mist_max_closed_vent_s",
        kind="numeric",
        min=120,
        max=900,
        default=600,
        fw_clamp_lo=120,
        fw_clamp_hi=900,
        esp_object_id="mist_max_closed_vent__s_",
        cfg_readback_object_id="cfg___mist_max_closed_vent__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Maximum time vent can stay closed during misting before thermal-relief burst.",
    ),
    "mist_vent_reopen_delay_s": TunableDef(
        name="mist_vent_reopen_delay_s",
        kind="numeric",
        min=0,
        max=120,
        default=45,
        fw_clamp_lo=0,
        fw_clamp_hi=120,
        esp_object_id="mist_vent_reopen_delay__s_",
        cfg_readback_object_id="cfg___mist_vent_reopen_delay__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Delay after mist completes before vent reopens (lets evap settle).",
    ),
    "mist_thermal_relief_s": TunableDef(
        name="mist_thermal_relief_s",
        kind="numeric",
        min=30,
        max=300,
        default=90,
        fw_clamp_lo=30,
        fw_clamp_hi=300,
        esp_object_id="mist_thermal_relief__s_",
        cfg_readback_object_id="cfg___mist_thermal_relief__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Mandatory vent-open relief duration if mist-closed-vent cap hit.",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Irrigation schedule (push_owner="operator"). Tier=2 across the board.
    # ─────────────────────────────────────────────────────────────────────
    "irrig_wall_start_hour": TunableDef(
        name="irrig_wall_start_hour",
        kind="numeric",
        min=0,
        max=23,
        default=6,
        fw_clamp_lo=0,
        fw_clamp_hi=23,
        esp_object_id="irrig_wall_start_hour",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Wall-drip schedule — operator configures.",
    ),
    "irrig_wall_start_min": TunableDef(
        name="irrig_wall_start_min",
        kind="numeric",
        min=0,
        max=59,
        default=0,
        fw_clamp_lo=0,
        fw_clamp_hi=59,
        esp_object_id="irrig_wall_start_min",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "irrig_wall_duration_min": TunableDef(
        name="irrig_wall_duration_min",
        kind="numeric",
        min=1,
        max=120,
        default=10,
        fw_clamp_lo=1,
        fw_clamp_hi=120,
        esp_object_id="irrig_wall_duration__min_",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "irrig_wall_fert_duration_min": TunableDef(
        name="irrig_wall_fert_duration_min",
        kind="numeric",
        min=0,
        max=60,
        default=5,
        fw_clamp_lo=0,
        fw_clamp_hi=60,
        esp_object_id="irrig_wall_fert_duration__min_",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "irrig_wall_fert_every_n": TunableDef(
        name="irrig_wall_fert_every_n",
        kind="numeric",
        min=0,
        max=30,
        default=0,
        fw_clamp_lo=0,
        fw_clamp_hi=30,
        esp_object_id="irrig_wall_fert_every_n_cycles",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Naming quirk: canonical drops '_cycles' suffix that SETPOINT_MAP key carries.",
    ),
    "irrig_wall_flush_min": TunableDef(
        name="irrig_wall_flush_min",
        kind="numeric",
        min=0,
        max=30,
        default=2,
        fw_clamp_lo=0,
        fw_clamp_hi=30,
        esp_object_id="irrig_wall_flush__min_",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "irrig_wall_interval_days": TunableDef(
        name="irrig_wall_interval_days",
        kind="numeric",
        min=1,
        max=14,
        default=1,
        fw_clamp_lo=1,
        fw_clamp_hi=14,
        esp_object_id="irrig_wall_interval__days_",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "irrig_center_start_hour": TunableDef(
        name="irrig_center_start_hour",
        kind="numeric",
        min=0,
        max=23,
        default=6,
        fw_clamp_lo=0,
        fw_clamp_hi=23,
        esp_object_id="irrig_center_start_hour",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "irrig_center_start_min": TunableDef(
        name="irrig_center_start_min",
        kind="numeric",
        min=0,
        max=59,
        default=30,
        fw_clamp_lo=0,
        fw_clamp_hi=59,
        esp_object_id="irrig_center_start_min",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "irrig_center_duration_min": TunableDef(
        name="irrig_center_duration_min",
        kind="numeric",
        min=1,
        max=120,
        default=10,
        fw_clamp_lo=1,
        fw_clamp_hi=120,
        esp_object_id="irrig_center_duration__min_",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "irrig_center_fert_duration_min": TunableDef(
        name="irrig_center_fert_duration_min",
        kind="numeric",
        min=0,
        max=60,
        default=5,
        fw_clamp_lo=0,
        fw_clamp_hi=60,
        esp_object_id="irrig_center_fert_duration__min_",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "irrig_center_fert_every_n": TunableDef(
        name="irrig_center_fert_every_n",
        kind="numeric",
        min=0,
        max=30,
        default=0,
        fw_clamp_lo=0,
        fw_clamp_hi=30,
        esp_object_id="irrig_center_fert_every_n_cycles",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Naming quirk: canonical drops '_cycles' suffix.",
    ),
    "irrig_center_flush_min": TunableDef(
        name="irrig_center_flush_min",
        kind="numeric",
        min=0,
        max=30,
        default=2,
        fw_clamp_lo=0,
        fw_clamp_hi=30,
        esp_object_id="irrig_center_flush__min_",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "irrig_center_interval_days": TunableDef(
        name="irrig_center_interval_days",
        kind="numeric",
        min=1,
        max=14,
        default=1,
        fw_clamp_lo=1,
        fw_clamp_hi=14,
        esp_object_id="irrig_center_interval__days_",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Economiser (enthalpy-based vent gating).
    # ─────────────────────────────────────────────────────────────────────
    "enthalpy_open": TunableDef(
        name="enthalpy_open",
        kind="numeric",
        min=-5.0,
        max=0.0,
        default=-2.0,
        fw_clamp_lo=-5.0,
        fw_clamp_hi=0.0,
        esp_object_id="enthalpy_open__kj_kg_",
        cfg_readback_object_id="cfg___enthalpy_open__kj_kg___",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Economiser opens when outdoor-indoor enthalpy ≤ this. In MCP TIER1.",
    ),
    "enthalpy_close": TunableDef(
        name="enthalpy_close",
        kind="numeric",
        min=-5.0,
        max=20.0,
        default=1.0,
        fw_clamp_lo=-5.0,
        fw_clamp_hi=20.0,
        esp_object_id="enthalpy_close__kj_kg_",
        cfg_readback_object_id="cfg___enthalpy_close__kj_kg___",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Economiser closes when enthalpy ≥ this. In MCP TIER1.",
    ),
    "site_pressure_hpa": TunableDef(
        name="site_pressure_hpa",
        kind="numeric",
        min=700,
        max=1100,
        default=840.0,
        fw_clamp_lo=700,
        fw_clamp_hi=1100,
        esp_object_id="site_pressure__hpa_",
        cfg_readback_object_id="cfg___site_pressure__hpa_",
        push_owner="operator",
        planner_pushable=False,
        tier=2,
        notes="Elevation-corrected barometric pressure for VPD calc. Site constant — not planner-pushable.",
    ),
    "sw_economiser_enabled": TunableDef(
        name="sw_economiser_enabled",
        kind="switch",
        default=1,
        esp_object_id="economiser_enabled",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Economiser master enable. Default ON.",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Operator switches (push_owner="operator", tier=2). Planner CAN push
    # (e.g. weather-skip toggle on storm forecast) but rarely does.
    # ─────────────────────────────────────────────────────────────────────
    "sw_irrigation_enabled": TunableDef(
        name="sw_irrigation_enabled",
        kind="switch",
        default=1,
        esp_object_id="irrigation_enabled",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Master irrigation enable.",
    ),
    "sw_irrigation_wall_enabled": TunableDef(
        name="sw_irrigation_wall_enabled",
        kind="switch",
        default=1,
        esp_object_id="irrigation_wall_enabled",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "sw_irrigation_center_enabled": TunableDef(
        name="sw_irrigation_center_enabled",
        kind="switch",
        default=1,
        esp_object_id="irrigation_center_enabled",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
    ),
    "sw_irrigation_weather_skip": TunableDef(
        name="sw_irrigation_weather_skip",
        kind="switch",
        default=1,
        esp_object_id="irrigation_weather_skip",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Skip irrigation on rainy-day forecast.",
    ),
    "sw_occupancy_inhibit": TunableDef(
        name="sw_occupancy_inhibit",
        kind="switch",
        default=1,
        esp_object_id="occupancy_mist_inhibit",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Block misting while greenhouse is occupied.",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Sprint-15 summer-vent gate (the class of tunable that repeatedly hit
    # the TIER1 drift bug). Definitive source-of-truth for min/max + clamps.
    # ─────────────────────────────────────────────────────────────────────
    "sw_summer_vent_enabled": TunableDef(
        name="sw_summer_vent_enabled",
        kind="switch",
        default=1,
        esp_object_id="summer_vent_enabled",
        cfg_readback_object_id="cfg_summer_vent_enabled",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Master switch for the sprint-15 outdoor-cooler-and-drier gate. "
        "Default ON: firmware behavior without it is wrong in summer.",
    ),
    "vent_prefer_temp_delta_f": TunableDef(
        name="vent_prefer_temp_delta_f",
        kind="numeric",
        min=2.0,
        max=15.0,
        default=5.0,
        fw_clamp_lo=2.0,
        fw_clamp_hi=15.0,
        esp_object_id="vent_prefer_temp_delta__f_",
        cfg_readback_object_id="cfg___vent_prefer_temp_delta__f_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Outdoor must be ≥ this many °F cooler than indoor for gate to fire.",
    ),
    "vent_prefer_dp_delta_f": TunableDef(
        name="vent_prefer_dp_delta_f",
        kind="numeric",
        min=2.0,
        max=15.0,
        default=5.0,
        fw_clamp_lo=2.0,
        fw_clamp_hi=15.0,
        esp_object_id="vent_prefer_dp_delta__f_",
        cfg_readback_object_id="cfg___vent_prefer_dp_delta__f_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Outdoor dewpoint must be ≥ this many °F below indoor DP for gate.",
    ),
    "outdoor_staleness_max_s": TunableDef(
        name="outdoor_staleness_max_s",
        kind="numeric",
        min=120,
        max=1800,
        default=600,
        fw_clamp_lo=120,
        fw_clamp_hi=1800,
        esp_object_id="outdoor_staleness_max__s_",
        cfg_readback_object_id="cfg___outdoor_staleness_max__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=2,
        notes="Gate disables when outdoor data older than this. Sprint-15.1 "
        "raised default 300→600 and floor 60→120 so dispatcher cadence "
        "jitter doesn't intermittently disqualify the gate.",
    ),
    "summer_vent_min_runtime_s": TunableDef(
        name="summer_vent_min_runtime_s",
        kind="numeric",
        min=60,
        max=600,
        default=180,
        fw_clamp_lo=60,
        fw_clamp_hi=600,
        esp_object_id="summer_vent_min_runtime__s_",
        cfg_readback_object_id="cfg___summer_vent_min_runtime__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=2,
    ),
    # ── Sprint-15.1 vent-close interlocks (fixes 4/5/7) ──────────────
    "sw_fog_closes_vent": TunableDef(
        name="sw_fog_closes_vent",
        kind="switch",
        default=1,
        esp_object_id="fog_closes_vent",
        cfg_readback_object_id=None,  # switch entity; state tracked in equipment_state not setpoint_snapshot
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Fog fires only when vent is closed. Default ON; disabling "
        "re-enables FW-9b emergency fog during VENTILATE (tradeoff).",
    ),
    "sw_mister_closes_vent": TunableDef(
        name="sw_mister_closes_vent",
        kind="switch",
        default=0,  # globals.yaml initial_value 'false'
        esp_object_id="mister_closes_vent",
        cfg_readback_object_id="sw_mister_closes_vent",  # Phase 1c routed the readback
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Mister fires only when vent is closed. Sprint-15.1 fix 5+7.",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Representative Tier 1 planner knobs — proof of pattern.
    # ─────────────────────────────────────────────────────────────────────
    "bias_heat": TunableDef(
        name="bias_heat",
        kind="numeric",
        min=-10.0,
        max=10.0,
        default=0.0,
        fw_clamp_lo=-10.0,
        fw_clamp_hi=10.0,  # controls.yaml clamp
        esp_object_id="bias_heat__f",  # entity_map.SETPOINT_MAP
        cfg_readback_object_id="cfg___bias_heat___f_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Note: validate_setpoints tightens this to [-5, +5] at ingest; "
        "controls.yaml accepts [-10, +10]. Registry uses the wider value.",
    ),
    "bias_cool": TunableDef(
        name="bias_cool",
        kind="numeric",
        min=-10.0,
        max=10.0,
        default=0.0,
        fw_clamp_lo=-10.0,
        fw_clamp_hi=10.0,
        esp_object_id="bias_cool__f",
        cfg_readback_object_id="cfg___bias_cool___f_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
    ),
    "min_heat_off_s": TunableDef(
        name="min_heat_off_s",
        kind="numeric",
        min=60,
        max=600,
        default=180,
        fw_clamp_lo=60,
        fw_clamp_hi=600,
        esp_object_id="min_heat_off__s_",
        cfg_readback_object_id="cfg___min_heat_off__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Sprint-15.1 fix 6: default 300→180. Clamp ceiling tightened 60→600 so planner can't walk past 10 min.",
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Phase-2 dwell gate.
    # ─────────────────────────────────────────────────────────────────────
    "sw_dwell_gate_enabled": TunableDef(
        name="sw_dwell_gate_enabled",
        kind="switch",
        default=0,
        esp_object_id="dwell_gate_enabled",
        cfg_readback_object_id=None,  # switch; state in equipment_state
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Master switch for Phase-2 mode-dwell gate. Default OFF for "
        "shadow-mode bake. Flip to ON after 14d replay+shadow validation.",
    ),
    "dwell_gate_ms": TunableDef(
        name="dwell_gate_ms",
        kind="numeric",
        min=60000,
        max=1800000,
        default=300000,
        fw_clamp_lo=60000,
        fw_clamp_hi=1800000,
        esp_object_id="dwell_gate_ms",
        cfg_readback_object_id=None,
        push_owner="planner",
        planner_pushable=True,
        tier=2,
        notes="Dwell hold duration. Default 5 min. Safety rails + R2-3 "
        "dry override + vpd_min_safe rescue preempt unconditionally.",
    ),
    "sw_fsm_controller_enabled": TunableDef(
        name="sw_fsm_controller_enabled",
        kind="switch",
        default=0,
        esp_object_id="fsm_controller_enabled",
        cfg_readback_object_id="cfg_fsm_controller_enabled",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Master switch for controller v2 band-first FSM. Default OFF so "
        "legacy firmware remains the rollback path.",
    ),
    "mist_backoff_s": TunableDef(
        name="mist_backoff_s",
        kind="numeric",
        min=60,
        max=3600,
        default=600,
        fw_clamp_lo=60,
        fw_clamp_hi=3600,
        esp_object_id="mist_backoff__s_",
        cfg_readback_object_id="cfg___mist_backoff__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Controller v2 lockout after sealed humidification times out. "
        "Suppresses another SEALED_MIST attempt without forcing venting.",
    ),
    "fog_escalation_kpa": TunableDef(
        name="fog_escalation_kpa",
        kind="numeric",
        min=0.1,
        max=1.0,
        default=0.4,
        fw_clamp_lo=0.1,
        fw_clamp_hi=1.0,  # controls.yaml clamp
        esp_object_id="fog_escalation__kpa_",
        cfg_readback_object_id="cfg___fog_escalation__kpa_",  # Phase 1c added readback
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="VPD delta above vpd_high that escalates from mist → fog.",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Derived views — ONE source of truth above, many consumers below.
# ─────────────────────────────────────────────────────────────────────────────


def _all_tunables() -> frozenset[str]:
    return frozenset(REGISTRY)


def _tier1() -> frozenset[str]:
    """Planner-accessible via MCP set_tunable. Replaces mcp/server.py TIER1."""
    return frozenset(n for n, d in REGISTRY.items() if d.planner_pushable and d.tier == 1)


def _planner_pushable() -> frozenset[str]:
    """Broader set: everything the planner CAN push (includes tier-2 escape hatch)."""
    return frozenset(n for n, d in REGISTRY.items() if d.planner_pushable)


def _setpoint_map() -> dict[str, str]:
    """ESPHome object_id → canonical name. Replaces ingestor.entity_map.SETPOINT_MAP."""
    return {d.esp_object_id: n for n, d in REGISTRY.items()}


def _cfg_readback_map() -> dict[str, str]:
    """cfg_* slug → canonical name. Replaces ingestor.entity_map.CFG_READBACK_MAP."""
    return {d.cfg_readback_object_id: n for n, d in REGISTRY.items() if d.cfg_readback_object_id}


# Phase 1b.2: expose as module attributes for consumers that already import
# computed-view style. `ALL_TUNABLES_REG` etc. coexist with the legacy
# `ALL_TUNABLES` in `tunables.py` during migration; Phase 1d flips the legacy
# module to import from here.
ALL_TUNABLES_REG: frozenset[str] = _all_tunables()
TIER1_REG: frozenset[str] = _tier1()
PLANNER_PUSHABLE_REG: frozenset[str] = _planner_pushable()
SETPOINT_MAP_REG: dict[str, str] = _setpoint_map()
CFG_READBACK_MAP_REG: dict[str, str] = _cfg_readback_map()


def get(name: str) -> TunableDef | None:
    """Lookup a tunable by canonical name. None if not registered."""
    return REGISTRY.get(name)
