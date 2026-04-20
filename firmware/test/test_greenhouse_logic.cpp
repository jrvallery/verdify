/*
 * test_greenhouse_logic.cpp — Native x86 tests for greenhouse controller logic.
 * Same code as ESP32. Tests all 11 fixes from 4-LLM review synthesis.
 *
 * Compile: g++ -std=c++17 -I../lib -o test_greenhouse test_greenhouse_logic.cpp
 */

#include "greenhouse_logic.h"
#include <cstdio>
#include <cstring>
#include <cassert>
#include <vector>
#include <cmath>

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST(name) \
    static void test_##name(); \
    static struct Register_##name { \
        Register_##name() { test_registry.push_back({#name, test_##name}); } \
    } reg_##name; \
    static void test_##name()

#define ASSERT_EQ(a, b) do { if ((a) != (b)) { printf("  FAIL: %s != %s (line %d)\n", #a, #b, __LINE__); tests_failed++; return; } } while(0)
#define ASSERT_TRUE(x) do { if (!(x)) { printf("  FAIL: %s (line %d)\n", #x, __LINE__); tests_failed++; return; } } while(0)
#define ASSERT_FALSE(x) ASSERT_TRUE(!(x))
#define PASS() tests_passed++

struct TestEntry { const char* name; void (*fn)(); };
static std::vector<TestEntry> test_registry;

static SensorInputs make_inputs(float temp, float vpd, float rh = 60.0f) {
    return { .temp_f = temp, .vpd_kpa = vpd, .rh_pct = rh,
             .dew_point_f = temp - 10.0f, .outdoor_rh_pct = 30.0f,
             .enthalpy_delta = -5.0f,
             .vpd_south = vpd, .vpd_west = vpd, .vpd_east = vpd,
             .local_hour = 12, .occupied = false,
             // Sprint-10 0.3: default to photoperiod=true since local_hour=12
             // is midday; night tests construct inputs explicitly.
             .is_photoperiod = true };
}

// Helper: run resolve_equipment with state
static RelayOutputs equip(Mode m, float t, float v, Setpoints sp = default_setpoints(), ControlState st = initial_state()) {
    return resolve_equipment(m, make_inputs(t, v), sp, st, true);
}

// ═══════════════════════════════════════════════════════════════
// CORE MODE TESTS
// ═══════════════════════════════════════════════════════════════

TEST(idle_when_in_band) {
    auto s = initial_state();
    ASSERT_EQ(determine_mode(make_inputs(72, 0.9), default_setpoints(), s, 5000), IDLE);
    PASS();
}

TEST(ventilate_when_hot) {
    auto s = initial_state();
    ASSERT_EQ(determine_mode(make_inputs(84, 0.9), default_setpoints(), s, 5000), VENTILATE);
    PASS();
}

TEST(sealed_after_dwell) {
    auto s = initial_state(); s.vpd_watch_timer_ms = 60000;
    ASSERT_EQ(determine_mode(make_inputs(72, 1.5), default_setpoints(), s, 5000), SEALED_MIST);
    PASS();
}

TEST(not_sealed_before_dwell) {
    auto s = initial_state(); s.vpd_watch_timer_ms = 30000;
    ASSERT_EQ(determine_mode(make_inputs(72, 1.5), default_setpoints(), s, 5000), IDLE);
    PASS();
}

TEST(safety_cool) {
    auto s = initial_state();
    ASSERT_EQ(determine_mode(make_inputs(96, 1), default_setpoints(), s, 5000), SAFETY_COOL);
    PASS();
}

TEST(safety_heat) {
    auto s = initial_state();
    ASSERT_EQ(determine_mode(make_inputs(44, 0.3), default_setpoints(), s, 5000), SAFETY_HEAT);
    PASS();
}

TEST(relief_after_sealed_max) {
    auto s = initial_state(); s.mode_prev = SEALED_MIST; s.sealed_timer_ms = 600000;
    ASSERT_EQ(determine_mode(make_inputs(72, 1.5), default_setpoints(), s, 5000), THERMAL_RELIEF);
    PASS();
}

TEST(dehum_when_vpd_low) {
    auto s = initial_state();
    ASSERT_EQ(determine_mode(make_inputs(72, 0.15), default_setpoints(), s, 5000), DEHUM_VENT);
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// FIX 1: mode_prev reads last cycle
// ═══════════════════════════════════════════════════════════════

TEST(fix1_mode_prev_tracks_correctly) {
    auto sp = default_setpoints(); auto s = initial_state();
    s.vpd_watch_timer_ms = 60000;
    // Cycle 1: enter SEALED_MIST
    Mode m1 = determine_mode(make_inputs(72, 1.5), sp, s, 5000);
    ASSERT_EQ(m1, SEALED_MIST);
    ASSERT_EQ(s.mode_prev, SEALED_MIST);
    // Cycle 2: VPD drops below exit → should see was_sealed=true and exit
    Mode m2 = determine_mode(make_inputs(72, 0.85), sp, s, 5000);
    ASSERT_EQ(m2, IDLE);
    PASS();
}

TEST(fix1_relief_to_idle_transition) {
    auto sp = default_setpoints(); auto s = initial_state();
    s.mode_prev = THERMAL_RELIEF; s.relief_timer_ms = 89000;
    // VPD resolved during relief
    Mode m = determine_mode(make_inputs(72, 0.8), sp, s, 5000);
    // Relief just expired, VPD is in band → should be IDLE
    ASSERT_EQ(m, IDLE);
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// FIX 2: VPD safety vs SAFETY_HEAT / THERMAL_RELIEF
// ═══════════════════════════════════════════════════════════════

TEST(fix2_vpd_safety_no_stomp_safety_heat) {
    auto s = initial_state();
    Mode m = determine_mode(make_inputs(40, 3.5), default_setpoints(), s, 5000);
    ASSERT_EQ(m, SAFETY_HEAT);
    PASS();
}

TEST(fix2_vpd_safety_no_stomp_thermal_relief) {
    auto s = initial_state(); s.mode_prev = THERMAL_RELIEF; s.relief_timer_ms = 45000;
    Mode m = determine_mode(make_inputs(72, 3.5), default_setpoints(), s, 5000);
    ASSERT_EQ(m, THERMAL_RELIEF);
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// FIX 3: Temperature hysteresis
// ═══════════════════════════════════════════════════════════════

TEST(fix3_ventilate_exit_hysteresis) {
    auto sp = default_setpoints(); sp.temp_high = 78; sp.temp_hysteresis = 1.5;
    auto s = initial_state();
    // Enter VENTILATE at 79°F
    determine_mode(make_inputs(79, 0.9), sp, s, 5000);
    ASSERT_EQ(s.mode, VENTILATE);
    // Drop to 77°F (still above 78-1.5=76.5) → stay
    determine_mode(make_inputs(77, 0.9), sp, s, 5000);
    ASSERT_EQ(s.mode, VENTILATE);
    // Drop to 76°F (below 76.5) → exit
    determine_mode(make_inputs(76, 0.9), sp, s, 5000);
    ASSERT_EQ(s.mode, IDLE);
    PASS();
}

TEST(fix3_heat_hysteresis) {
    // IN-12 (Sprint 19): fixed after commit 2b61ee6 swapped the inverted
    // dH2 / heat_hysteresis thresholds. Sprint-9 P1#7: S2 is now latched
    // via ControlState.heat2_latched; the fresh state passed by equip()
    // starts with heat2_latched=false, so S1-only is the only behavior
    // exercisable without going through determine_mode. See
    // s9_heat2_latches_* tests for the S2 latch lifecycle.
    auto sp = default_setpoints(); sp.temp_low = 58; sp.heat_hysteresis = 1.0;
    // S1 (electric) threshold: Tlow + heat_hysteresis = 59°F
    // 57.5°F → S1 on (below threshold), S2 not latched yet
    auto out = equip(IDLE, 57.5, 0.9, sp);
    ASSERT_TRUE(out.heat1);
    ASSERT_FALSE(out.heat2);
    auto out2 = equip(IDLE, 56.5, 0.9, sp);
    ASSERT_TRUE(out2.heat1);
    ASSERT_FALSE(out2.heat2);
    // Even at 52°F (below S2 threshold), fresh state with latched=false
    // does not fire S2 — the latch must be set by determine_mode first.
    auto out3 = equip(IDLE, 52.0, 0.9, sp);
    ASSERT_TRUE(out3.heat1);
    ASSERT_FALSE(out3.heat2);
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// FIX 4: DEHUM_VENT sticky hysteresis
// ═══════════════════════════════════════════════════════════════

TEST(fix4_dehum_stays_until_vpd_low) {
    auto sp = default_setpoints(); auto s = initial_state();
    // Enter DEHUM at VPD=0.15 (below vpd_low - HV = 0.2)
    determine_mode(make_inputs(72, 0.15), sp, s, 5000);
    ASSERT_EQ(s.mode, DEHUM_VENT);
    // VPD rises to 0.35 (still below vpd_low=0.5) → stay
    determine_mode(make_inputs(72, 0.35), sp, s, 5000);
    ASSERT_EQ(s.mode, DEHUM_VENT);
    // VPD rises to 0.5 (at vpd_low) → exit
    determine_mode(make_inputs(72, 0.5), sp, s, 5000);
    ASSERT_EQ(s.mode, IDLE);
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// FIX 5: Relief exit runs full cascade
// ═══════════════════════════════════════════════════════════════

TEST(fix5_relief_exits_to_ventilate_when_hot) {
    auto sp = default_setpoints(); auto s = initial_state();
    s.mode_prev = THERMAL_RELIEF; s.relief_timer_ms = 89000;
    // VPD resolved but temp is high → should VENTILATE, not IDLE
    Mode m = determine_mode(make_inputs(84, 0.8), sp, s, 5000);
    ASSERT_EQ(m, VENTILATE);
    PASS();
}

TEST(fix5_relief_exits_to_sealed_when_vpd_high) {
    auto sp = default_setpoints(); auto s = initial_state();
    s.mode_prev = THERMAL_RELIEF; s.relief_timer_ms = 89000;
    s.vpd_watch_timer_ms = 60000;  // dwell satisfied
    // VPD still high → should re-seal
    Mode m = determine_mode(make_inputs(72, 1.5), sp, s, 5000);
    ASSERT_EQ(m, SEALED_MIST);
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// FIX 6: IDLE econ heating is capped
// ═══════════════════════════════════════════════════════════════

TEST(fix6_econ_heat_electric_only) {
    auto sp = default_setpoints(); sp.econ_block = true;
    auto out = equip(IDLE, 72, 0.3, sp);
    // Electric only for VPD rescue, no gas
    ASSERT_TRUE(out.heat1);
    ASSERT_FALSE(out.heat2);
    PASS();
}

TEST(fix6_econ_heat_capped_by_temp) {
    auto sp = default_setpoints(); sp.econ_block = true;
    // Temp 80°F is near Thigh (82). 80 >= 82-5=77 → too hot for econ heating
    auto out = equip(IDLE, 80, 0.3, sp);
    ASSERT_FALSE(out.heat1);  // temp too high for econ heating
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// FIX 7: Watch timer suspended in safety
// ═══════════════════════════════════════════════════════════════

TEST(fix7_watch_timer_frozen_during_safety) {
    auto sp = default_setpoints(); auto s = initial_state();
    s.mode_prev = SAFETY_COOL;
    // VPD is above band during safety cool — watch timer should NOT increment
    determine_mode(make_inputs(96, 1.5), sp, s, 5000);
    ASSERT_EQ(s.vpd_watch_timer_ms, 0u);
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// FIX 8: SENSOR_FAULT
// ═══════════════════════════════════════════════════════════════

TEST(fix8_nan_temp) {
    auto s = initial_state();
    auto in = make_inputs(NAN, 0.9);
    ASSERT_EQ(determine_mode(in, default_setpoints(), s, 5000), SENSOR_FAULT);
    PASS();
}

TEST(fix8_nan_vpd) {
    auto s = initial_state();
    auto in = make_inputs(72, NAN);
    ASSERT_EQ(determine_mode(in, default_setpoints(), s, 5000), SENSOR_FAULT);
    PASS();
}

TEST(fix8_sensor_fault_equipment) {
    // R2-1: ALL relays off on sensor fault — no blind actuation
    auto out = equip(SENSOR_FAULT, 72, 0.9);
    ASSERT_FALSE(out.heat1);
    ASSERT_FALSE(out.heat2);
    ASSERT_FALSE(out.vent);
    ASSERT_FALSE(out.fan1);
    ASSERT_FALSE(out.fog);
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// R2 FIXES — Round 2 review
// ═══════════════════════════════════════════════════════════════

TEST(r2_2_sensor_fault_preserves_mode_prev) {
    auto sp = default_setpoints(); auto s = initial_state();
    // Enter VENTILATE
    determine_mode(make_inputs(84, 0.9), sp, s, 5000);
    ASSERT_EQ(s.mode_prev, VENTILATE);
    // Transient sensor fault
    auto bad = make_inputs(NAN, 0.9);
    determine_mode(bad, sp, s, 5000);
    ASSERT_EQ(s.mode, SENSOR_FAULT);
    // mode_prev should STILL be VENTILATE (not SENSOR_FAULT)
    ASSERT_EQ(s.mode_prev, VENTILATE);
    PASS();
}

TEST(r2_3_vpd_override_no_stomp_ventilate) {
    auto sp = default_setpoints(); auto s = initial_state();
    // Temp is hot (needs cooling) AND VPD is extreme
    auto in = make_inputs(84, 3.5);
    Mode m = determine_mode(in, sp, s, 5000);
    // Should be VENTILATE (cooling takes priority), not SEALED_MIST
    ASSERT_EQ(m, VENTILATE);
    PASS();
}

TEST(r2_4_implausible_temp_triggers_fault) {
    auto s = initial_state();
    auto in = make_inputs(-127, 0.9);  // disconnected SHT sensor
    ASSERT_EQ(determine_mode(in, default_setpoints(), s, 5000), SENSOR_FAULT);
    PASS();
}

TEST(r2_4_implausible_rh_triggers_fault) {
    auto s = initial_state();
    SensorInputs in = make_inputs(72, 0.9, 105.0f);  // RH > 100%
    ASSERT_EQ(determine_mode(in, default_setpoints(), s, 5000), SENSOR_FAULT);
    PASS();
}

TEST(r2_5_occupancy_blocks_fog) {
    auto sp = default_setpoints(); sp.occupancy_inhibit = true;
    auto s = initial_state(); s.mist_stage = MIST_FOG;
    SensorInputs in = make_inputs(72, 1.7, 60);
    in.occupied = true;
    auto out = resolve_equipment(SEALED_MIST, in, sp, s, true);
    ASSERT_FALSE(out.fog);  // occupied + inhibit → no fog
    PASS();
}

TEST(r2_6_relief_cycle_forces_ventilate) {
    auto sp = default_setpoints(); sp.max_relief_cycles = 3;
    auto s = initial_state();
    s.relief_cycle_count = 3;  // at the limit
    s.vpd_watch_timer_ms = 60000;
    // VPD wants seal but relief cycles exhausted → force VENTILATE
    Mode m = determine_mode(make_inputs(72, 1.5), sp, s, 5000);
    ASSERT_EQ(m, VENTILATE);
    PASS();
}

TEST(r2_8_dehum_respects_econ_block_change) {
    auto sp = default_setpoints(); auto s = initial_state();
    // Enter DEHUM
    determine_mode(make_inputs(72, 0.15), sp, s, 5000);
    ASSERT_EQ(s.mode, DEHUM_VENT);
    // Econ blocks mid-cycle
    sp.econ_block = true;
    determine_mode(make_inputs(72, 0.35), sp, s, 5000);
    // Should exit DEHUM because econ now blocks venting
    ASSERT_EQ(s.mode, IDLE);
    PASS();
}

TEST(r2_9_fog_stage_blocked_by_time_window) {
    auto sp = default_setpoints(); auto s = initial_state();
    s.mode_prev = SEALED_MIST; s.sealed_timer_ms = 100000;
    s.mist_stage = MIST_S2; s.mist_stage_timer_ms = 0;
    // VPD demands fog BUT it's outside the fog time window
    SensorInputs in = make_inputs(72, 1.7, 60);
    in.local_hour = 22;  // 10 PM — outside 7-17 window
    determine_mode(in, sp, s, 5000);
    // Should NOT escalate to MIST_FOG
    ASSERT_EQ(s.mist_stage, MIST_S2);
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// FIX 9: Mist stage progression
// ═══════════════════════════════════════════════════════════════

TEST(fix9_mist_stage_s1_on_seal) {
    auto sp = default_setpoints(); auto s = initial_state();
    s.vpd_watch_timer_ms = 60000;
    determine_mode(make_inputs(72, 1.5), sp, s, 5000);
    ASSERT_EQ(s.mist_stage, MIST_S1);
    PASS();
}

TEST(fix9_mist_stage_s1_to_s2) {
    auto sp = default_setpoints(); sp.mist_s2_delay_ms = 300000;
    auto s = initial_state();
    s.mode_prev = SEALED_MIST; s.sealed_timer_ms = 100000;
    s.mist_stage = MIST_S1; s.mist_stage_timer_ms = 300000;
    // VPD still above band → should escalate to S2
    determine_mode(make_inputs(72, 1.5), sp, s, 5000);
    ASSERT_EQ(s.mist_stage, MIST_S2);
    PASS();
}

TEST(fix9_mist_stage_s2_to_fog) {
    auto sp = default_setpoints(); sp.fog_escalation_kpa = 0.4;
    auto s = initial_state();
    s.mode_prev = SEALED_MIST; s.sealed_timer_ms = 100000;
    s.mist_stage = MIST_S2; s.mist_stage_timer_ms = 0;
    // VPD = 1.7 > vpd_high(1.2) + fog_escalation(0.4) = 1.6 → FOG
    determine_mode(make_inputs(72, 1.7), sp, s, 5000);
    ASSERT_EQ(s.mist_stage, MIST_FOG);
    PASS();
}

TEST(fix9_mist_resets_on_seal_exit) {
    auto sp = default_setpoints(); auto s = initial_state();
    s.mode_prev = SEALED_MIST; s.sealed_timer_ms = 100000;
    s.mist_stage = MIST_S2;
    // VPD drops below exit → exits sealed, mist resets
    determine_mode(make_inputs(72, 0.85), sp, s, 5000);
    ASSERT_EQ(s.mist_stage, MIST_WATCH);
    PASS();
}

TEST(fix9_fog_in_equipment_reads_mist_stage) {
    auto sp = default_setpoints();
    auto s = initial_state(); s.mist_stage = MIST_FOG;
    auto in = make_inputs(72, 1.7, 60);
    auto out = resolve_equipment(SEALED_MIST, in, sp, s, true);
    ASSERT_TRUE(out.fog);
    PASS();
}

TEST(fix9_no_fog_when_not_mist_fog_stage) {
    auto sp = default_setpoints();
    auto s = initial_state(); s.mist_stage = MIST_S2;
    auto in = make_inputs(72, 1.7, 60);
    auto out = resolve_equipment(SEALED_MIST, in, sp, s, true);
    ASSERT_FALSE(out.fog);  // not in MIST_FOG stage
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// INVARIANT SWEEPS
// ═══════════════════════════════════════════════════════════════

TEST(no_open_vent_misting_ever) {
    auto sp = default_setpoints(); int v = 0;
    for (float t = 40; t <= 100; t += 2)
        for (float vpd = 0.1f; vpd <= 3.5f; vpd += 0.1f) {
            auto s = initial_state(); s.vpd_watch_timer_ms = 60000;
            Mode m = determine_mode(make_inputs(t, vpd), sp, s, 5000);
            auto out = resolve_equipment(m, make_inputs(t, vpd), sp, s, true);
            if (m == SEALED_MIST && out.vent) v++;
            if (m == SEALED_MIST && (out.fan1 || out.fan2)) v++;
        }
    ASSERT_EQ(v, 0); PASS();
}

TEST(no_heater_with_vent) {
    auto sp = default_setpoints(); int v = 0;
    for (float t = 40; t <= 100; t += 2)
        for (float vpd = 0.1f; vpd <= 3.5f; vpd += 0.1f) {
            auto s = initial_state(); s.vpd_watch_timer_ms = 60000;
            Mode m = determine_mode(make_inputs(t, vpd), sp, s, 5000);
            auto out = resolve_equipment(m, make_inputs(t, vpd), sp, s, true);
            if (out.vent && (out.heat1 || out.heat2)) v++;
        }
    ASSERT_EQ(v, 0); PASS();
}

TEST(no_fan_without_vent) {
    // Sprint-9 P2#11: SAFETY_HEAT intentionally runs the lead fan for
    // canopy circulation while the vent stays closed (keep heat in).
    // Whitelist it — the invariant still holds for every normal mode.
    auto sp = default_setpoints(); int v = 0;
    for (float t = 40; t <= 100; t += 2)
        for (float vpd = 0.1f; vpd <= 3.5f; vpd += 0.1f) {
            auto s = initial_state(); s.vpd_watch_timer_ms = 60000;
            Mode m = determine_mode(make_inputs(t, vpd), sp, s, 5000);
            auto out = resolve_equipment(m, make_inputs(t, vpd), sp, s, true);
            if (m == SAFETY_HEAT) continue;
            if (!out.vent && (out.fan1 || out.fan2)) v++;
        }
    ASSERT_EQ(v, 0); PASS();
}

// ═══════════════════════════════════════════════════════════════
// SCENARIO: Cold night
// ═══════════════════════════════════════════════════════════════

TEST(cold_night_no_vent_oscillation) {
    auto sp = default_setpoints(); sp.temp_high = 78; sp.bias_cool = 3;
    auto s = initial_state();
    float temps[] = {60,62,64,66,68,70,72,74,76,78,80,79,78,76,74,72,70,68,66,64,62,60};
    int vent = 0;
    for (float t : temps) {
        Mode m = determine_mode(make_inputs(t, 0.6f+(t-60)*0.02f), sp, s, 5000);
        auto out = resolve_equipment(m, make_inputs(t, 0.6f+(t-60)*0.02f), sp, s, true);
        if (out.vent) vent++;
    }
    ASSERT_EQ(vent, 0); PASS();
}

// ═══════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════
// FW-7/8/9: SEALED_MIST SAFETY TESTS
// ═══════════════════════════════════════════════════════════════

TEST(fw7_sealed_mist_temp_guard) {
    // SEALED_MIST should NOT engage when temp is within 5°F of safety_max
    auto sp = default_setpoints();
    sp.safety_max = 95.0f;
    sp.vpd_high = 1.0f;
    auto s = initial_state();
    // VPD above band at 91°F (within 5°F of safety_max=95)
    auto in = make_inputs(91.0f, 1.5f);
    // Run enough cycles to pass vpd_watch_dwell
    for (int i = 0; i < 15; i++) determine_mode(in, sp, s, 5000);
    // Should NOT be in SEALED_MIST — too hot
    ASSERT_TRUE(s.mode != SEALED_MIST);
    // At 85°F (safe margin), it SHOULD seal
    s = initial_state();
    in = make_inputs(85.0f, 1.5f);
    for (int i = 0; i < 15; i++) determine_mode(in, sp, s, 5000);
    ASSERT_EQ(s.mode, SEALED_MIST);
    PASS();
}

TEST(fw7_sealed_mist_exit_on_high_temp) {
    // Enter SEALED_MIST at safe temp, then temp climbs — should exit
    auto sp = default_setpoints();
    sp.safety_max = 95.0f;
    sp.vpd_high = 1.0f;
    auto s = initial_state();
    // Enter at 80°F
    auto in = make_inputs(80.0f, 1.5f);
    for (int i = 0; i < 15; i++) determine_mode(in, sp, s, 5000);
    ASSERT_EQ(s.mode, SEALED_MIST);
    // Temp climbs to 91°F (within 5°F of safety_max) — should exit to THERMAL_RELIEF
    in = make_inputs(91.0f, 1.5f);
    Mode m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, THERMAL_RELIEF);
    PASS();
}

TEST(fw8_relief_latch_timeout) {
    // After max_relief_cycles exhausted, controller latches VENTILATE.
    // After 30 minutes (360 × 5s cycles), counter should reset.
    auto sp = default_setpoints();
    sp.max_relief_cycles = 3;
    sp.vpd_high = 1.0f;
    sp.vpd_watch_dwell_ms = 5000;
    auto s = initial_state();
    s.relief_cycle_count = 3;  // Already exhausted
    auto in = make_inputs(75.0f, 1.5f);  // VPD above band, temp safe
    // Run through the dwell period
    for (int i = 0; i < 2; i++) determine_mode(in, sp, s, 5000);
    // Should be latched in VENTILATE
    ASSERT_EQ(s.mode, VENTILATE);
    ASSERT_TRUE(s.relief_cycle_count >= 3);
    // Run 360 more cycles (30 minutes at 5s each)
    for (int i = 0; i < 360; i++) determine_mode(in, sp, s, 5000);
    // Latch timer should have reset the counter
    ASSERT_EQ(s.relief_cycle_count, (uint32_t)0);
    // Next cycle with VPD above band should re-enter SEALED_MIST
    determine_mode(in, sp, s, 5000);
    ASSERT_EQ(s.mode, SEALED_MIST);
    PASS();
}

TEST(fw9b_ventilate_fog_on_vpd_emergency) {
    // When VPD > vpd_max_safe during VENTILATE, fog should fire (full battery)
    auto sp = default_setpoints();
    sp.vpd_max_safe = 3.0f;
    sp.fog_rh_ceiling = 90.0f;
    sp.fog_min_temp = 55.0f;
    sp.fog_window_start = 7;
    sp.fog_window_end = 17;
    auto s = initial_state();
    // 85°F, VPD 3.2 (above vpd_max_safe), 25% RH, hour 14 (in fog window)
    auto in = make_inputs(85.0f, 3.2f, 25.0f);
    auto out = resolve_equipment(VENTILATE, in, sp, s, true);
    ASSERT_TRUE(out.fog);   // Fog should be ON
    ASSERT_TRUE(out.vent);  // Vent still open (VENTILATE mode)
    ASSERT_TRUE(out.fan1);  // Fans running
    // VPD at 2.5 (below vpd_max_safe) — no fog
    in = make_inputs(85.0f, 2.5f, 35.0f);
    out = resolve_equipment(VENTILATE, in, sp, s, true);
    ASSERT_FALSE(out.fog);
    PASS();
}

// ═══════════════════════════════════════════════════════════════
// OBS-1e — evaluate_overrides() — Sprint 16 observability
// One test per silent override. Each test asserts BOTH that the
// flag fires when the override is active AND that it stays clear
// when the override's "desire trigger" is not met (zero false positives).
// ═══════════════════════════════════════════════════════════════

TEST(obs1e_occupancy_blocks_moisture_fires_in_seal) {
    auto sp = default_setpoints(); sp.occupancy_inhibit = true;
    auto s = initial_state(); s.vpd_watch_timer_ms = 60000;
    auto in = make_inputs(72.0f, 1.5f); in.occupied = true;
    auto f = evaluate_overrides(in, sp, s, SEALED_MIST);
    ASSERT_TRUE(f.occupancy_blocks_moisture);
    PASS();
}

TEST(obs1e_occupancy_quiet_when_nothing_wanted) {
    auto sp = default_setpoints(); sp.occupancy_inhibit = true;
    auto s = initial_state();
    auto in = make_inputs(72.0f, 0.9f); in.occupied = true;  // in-band, nobody wants mist
    auto f = evaluate_overrides(in, sp, s, IDLE);
    ASSERT_FALSE(f.occupancy_blocks_moisture);
    PASS();
}

TEST(obs1e_fog_gate_rh_fires) {
    auto sp = default_setpoints();
    auto s = initial_state(); s.mist_stage = MIST_S2; s.vpd_watch_timer_ms = 60000;
    auto in = make_inputs(72.0f, sp.vpd_high + sp.fog_escalation_kpa + 0.1f, 95.0f);
    auto f = evaluate_overrides(in, sp, s, SEALED_MIST);
    ASSERT_TRUE(f.fog_gate_rh);
    ASSERT_FALSE(f.fog_gate_temp);
    ASSERT_FALSE(f.fog_gate_window);
    PASS();
}

TEST(obs1e_fog_gate_temp_fires) {
    auto sp = default_setpoints();
    auto s = initial_state(); s.mist_stage = MIST_S2; s.vpd_watch_timer_ms = 60000;
    auto in = make_inputs(sp.fog_min_temp - 2.0f, sp.vpd_high + sp.fog_escalation_kpa + 0.1f, 50.0f);
    auto f = evaluate_overrides(in, sp, s, SEALED_MIST);
    ASSERT_TRUE(f.fog_gate_temp);
    ASSERT_FALSE(f.fog_gate_rh);
    PASS();
}

TEST(obs1e_fog_gate_window_fires) {
    auto sp = default_setpoints();
    auto s = initial_state(); s.mist_stage = MIST_S2; s.vpd_watch_timer_ms = 60000;
    auto in = make_inputs(72.0f, sp.vpd_high + sp.fog_escalation_kpa + 0.1f, 50.0f);
    in.local_hour = sp.fog_window_end;  // one past close
    auto f = evaluate_overrides(in, sp, s, SEALED_MIST);
    ASSERT_TRUE(f.fog_gate_window);
    PASS();
}

TEST(obs1e_fog_gate_quiet_when_not_in_s2) {
    auto sp = default_setpoints();
    auto s = initial_state(); s.mist_stage = MIST_S1;  // not S2
    auto in = make_inputs(72.0f, sp.vpd_high + sp.fog_escalation_kpa + 0.1f, 95.0f);
    auto f = evaluate_overrides(in, sp, s, SEALED_MIST);
    ASSERT_FALSE(f.fog_gate_rh);
    PASS();
}

TEST(obs1e_relief_cycle_breaker_fires) {
    auto sp = default_setpoints();
    auto s = initial_state();
    s.vpd_watch_timer_ms = 60000;
    s.relief_cycle_count = sp.max_relief_cycles;  // at the ceiling
    auto in = make_inputs(72.0f, 1.5f);
    auto f = evaluate_overrides(in, sp, s, VENTILATE);
    ASSERT_TRUE(f.relief_cycle_breaker);
    PASS();
}

TEST(obs1e_relief_cycle_breaker_quiet_below_ceiling) {
    auto sp = default_setpoints();
    auto s = initial_state();
    s.vpd_watch_timer_ms = 60000;
    s.relief_cycle_count = 1;  // plenty of headroom
    auto in = make_inputs(72.0f, 1.5f);
    auto f = evaluate_overrides(in, sp, s, SEALED_MIST);
    ASSERT_FALSE(f.relief_cycle_breaker);
    PASS();
}

TEST(obs1e_seal_blocked_temp_fires) {
    auto sp = default_setpoints();
    auto s = initial_state(); s.vpd_watch_timer_ms = 60000;
    // within 5°F of safety_max (default 95°F) — planner wants seal, firmware won't
    auto in = make_inputs(sp.safety_max - 3.0f, 1.5f);
    auto f = evaluate_overrides(in, sp, s, VENTILATE);
    ASSERT_TRUE(f.seal_blocked_temp);
    PASS();
}

TEST(obs1e_seal_blocked_temp_quiet_when_cool) {
    auto sp = default_setpoints();
    auto s = initial_state(); s.vpd_watch_timer_ms = 60000;
    auto in = make_inputs(72.0f, 1.5f);
    auto f = evaluate_overrides(in, sp, s, SEALED_MIST);
    ASSERT_FALSE(f.seal_blocked_temp);
    PASS();
}

TEST(obs1e_vpd_dry_override_fires_when_r23_forces_seal) {
    // OBS-1e patch: the override is set by determine_mode()'s R2-3 path.
    // Start in IDLE with zero dwell — planner would never seal yet —
    // but VPD climbs above vpd_max_safe. R2-3 forces SEALED_MIST and
    // sets dry_override_active. evaluate_overrides reads the flag.
    auto sp = default_setpoints();
    auto s = initial_state();
    s.vpd_watch_timer_ms = 0;
    auto in = make_inputs(72.0f, sp.vpd_max_safe + 0.2f);
    Mode m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, SEALED_MIST);           // R2-3 forced the seal
    ASSERT_TRUE(s.dry_override_active);  // flag set during determine_mode
    auto f = evaluate_overrides(in, sp, s, m);
    ASSERT_TRUE(f.vpd_dry_override);
    PASS();
}

TEST(obs1e_vpd_dry_override_quiet_when_planner_already_sealed) {
    // If we're already in SEALED_MIST via the planner's dwell, R2-3's
    // preconditions still hold but the transition isn't a forced override
    // — state.dry_override_active stays false because pre_r23_mode was
    // already SEALED_MIST.
    auto sp = default_setpoints();
    auto s = initial_state();
    s.vpd_watch_timer_ms = 60000;    // dwell mature
    s.mode_prev = SEALED_MIST;       // already sealed last cycle
    auto in = make_inputs(72.0f, sp.vpd_max_safe + 0.2f);
    Mode m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, SEALED_MIST);
    ASSERT_FALSE(s.dry_override_active);
    auto f = evaluate_overrides(in, sp, s, m);
    ASSERT_FALSE(f.vpd_dry_override);
    PASS();
}

TEST(obs1e_vpd_dry_override_clears_on_next_cycle_when_conditions_pass) {
    // Once VPD drops back below vpd_max_safe, dry_override_active must
    // reset to false so a stale flag doesn't linger.
    auto sp = default_setpoints();
    auto s = initial_state();
    s.vpd_watch_timer_ms = 0;
    auto in1 = make_inputs(72.0f, sp.vpd_max_safe + 0.2f);
    determine_mode(in1, sp, s, 5000);
    ASSERT_TRUE(s.dry_override_active);
    // Next cycle: VPD in-band, no R2-3 trigger
    auto in2 = make_inputs(72.0f, 0.9f);
    determine_mode(in2, sp, s, 5000);
    ASSERT_FALSE(s.dry_override_active);
    PASS();
}

TEST(obs1e_all_quiet_on_idle_in_band) {
    auto sp = default_setpoints();
    auto s = initial_state();
    auto in = make_inputs(72.0f, 0.9f);
    auto f = evaluate_overrides(in, sp, s, IDLE);
    ASSERT_FALSE(f.occupancy_blocks_moisture);
    ASSERT_FALSE(f.fog_gate_rh);
    ASSERT_FALSE(f.fog_gate_temp);
    ASSERT_FALSE(f.fog_gate_window);
    ASSERT_FALSE(f.relief_cycle_breaker);
    ASSERT_FALSE(f.seal_blocked_temp);
    ASSERT_FALSE(f.vpd_dry_override);
    PASS();
}

// ═══════════════════════════════════════════════════════════════════
// Sprint-8 — R2-3 state preservation + midnight-wrap fog window
// ═══════════════════════════════════════════════════════════════════

TEST(s8_r23_preserves_mist_stage_when_already_sealed) {
    // Pre-sprint-8: R2-3 unconditionally reset mist_stage to MIST_S1,
    // demoting peak MIST_FOG back to S1 at the exact moment VPD was
    // worst. Now: state preserved when pre_r23_mode == SEALED_MIST.
    auto sp = default_setpoints();
    auto s = initial_state();
    s.mode_prev = SEALED_MIST;
    s.mist_stage = MIST_FOG;
    s.mist_stage_timer_ms = 45000;
    s.sealed_timer_ms = 300000;
    s.vpd_watch_timer_ms = 60000;  // dwell mature
    auto in = make_inputs(72.0f, sp.vpd_max_safe + 0.2f);
    Mode m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, SEALED_MIST);
    ASSERT_EQ(s.mist_stage, MIST_FOG);  // NOT demoted
    ASSERT_TRUE(s.mist_stage_timer_ms >= 45000);  // NOT reset
    ASSERT_FALSE(s.dry_override_active);  // not a forced transition
    PASS();
}

TEST(s8_r23_preserves_sealed_timer_under_sustained_dryness) {
    // Pre-sprint-8: sealed_timer_ms was reset to dt_ms every cycle
    // while R2-3 fired, making sealed_max_ms unreachable and defeating
    // the THERMAL_RELIEF backstop. Post: timer accumulates normally, and
    // the state machine hits THERMAL_RELIEF once sealed_timer >= max.
    auto sp = default_setpoints();
    auto s = initial_state();
    s.mode_prev = SEALED_MIST;
    s.mist_stage = MIST_FOG;
    s.sealed_timer_ms = sp.sealed_max_ms - 5000;  // 5 s from max
    s.vpd_watch_timer_ms = 60000;
    auto in = make_inputs(72.0f, sp.vpd_max_safe + 0.2f);  // R2-3 trigger
    // Tick 1 (dt=10s): normal accumulator advances sealed_timer past max.
    // R2-3 fires but no longer resets the timer (sprint-8 fix).
    Mode m = determine_mode(in, sp, s, 10000);
    ASSERT_EQ(m, SEALED_MIST);
    ASSERT_TRUE(s.sealed_timer_ms > sp.sealed_max_ms);
    // Tick 2: the was_sealed branch now sees sealed_timer_ms >= max and
    // transitions to THERMAL_RELIEF. Pre-sprint-8 this path was
    // permanently unreachable under sustained R2-3 triggering.
    m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, THERMAL_RELIEF);
    PASS();
}

TEST(s8_r23_still_forces_seal_from_idle) {
    // Sanity: the non-sealed path still seeds mist_stage and
    // sealed_timer as before. Regression check on the main R2-3 flow.
    auto sp = default_setpoints();
    auto s = initial_state();  // mode_prev = IDLE, no dwell maturity
    auto in = make_inputs(72.0f, sp.vpd_max_safe + 0.2f);
    Mode m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, SEALED_MIST);
    ASSERT_EQ(s.mist_stage, MIST_S1);  // fresh seal seeds S1
    ASSERT_EQ(s.sealed_timer_ms, 5000u);
    ASSERT_EQ(s.vpd_watch_timer_ms, sp.vpd_watch_dwell_ms);
    ASSERT_TRUE(s.dry_override_active);  // this IS a forced override
    PASS();
}

TEST(s8_fog_window_wraps_midnight) {
    // Pre-sprint-8: a window crossing midnight (start > end) evaluated
    // to (hour < start || hour >= end) == true for every hour, gating
    // fog 24/7. Now: (hour >= start || hour < end) inside the wrap.
    auto sp = default_setpoints();
    sp.fog_window_start = 22;
    sp.fog_window_end = 6;
    auto s = initial_state();
    s.mist_stage = MIST_FOG;
    auto in = make_inputs(72.0f, 1.7f);

    // Inside the wrap — fog permitted
    in.local_hour = 23;
    ASSERT_TRUE(fog_permitted(in, sp));
    in.local_hour = 0;
    ASSERT_TRUE(fog_permitted(in, sp));
    in.local_hour = 5;
    ASSERT_TRUE(fog_permitted(in, sp));

    // Outside the wrap — fog gated
    in.local_hour = 6;   // inclusive end
    ASSERT_FALSE(fog_permitted(in, sp));
    in.local_hour = 12;
    ASSERT_FALSE(fog_permitted(in, sp));
    in.local_hour = 21;  // one hour before start
    ASSERT_FALSE(fog_permitted(in, sp));

    // Non-wrapping window (start <= end) still works
    sp.fog_window_start = 7;
    sp.fog_window_end = 17;
    in.local_hour = 12;
    ASSERT_TRUE(fog_permitted(in, sp));
    in.local_hour = 17;  // inclusive end
    ASSERT_FALSE(fog_permitted(in, sp));
    in.local_hour = 6;
    ASSERT_FALSE(fog_permitted(in, sp));
    PASS();
}

// ═══════════════════════════════════════════════════════════════════
// Sprint-9 — Heat S2 latch + validate_setpoints relational + SAFETY_HEAT fan
// ═══════════════════════════════════════════════════════════════════

TEST(s9_heat2_latch_sets_when_below_s2_threshold) {
    auto sp = default_setpoints();
    sp.temp_low = 58.0f;
    sp.dH2 = 5.0f;  // S2 threshold = 53°F
    auto s = initial_state();
    ASSERT_FALSE(s.heat2_latched);
    // 52°F → below Tlow - dH2 → latch sets
    determine_mode(make_inputs(52.0f, 0.9f), sp, s, 5000);
    ASSERT_TRUE(s.heat2_latched);
    // resolve_equipment honors the latch
    auto out = resolve_equipment(IDLE, make_inputs(52.0f, 0.9f), sp, s, true);
    ASSERT_TRUE(out.heat1);
    ASSERT_TRUE(out.heat2);
    PASS();
}

TEST(s9_heat2_latches_through_minor_fluctuation) {
    // Pre-sprint-9: a temp oscillating between 56 and 54 (in the band
    // between S2-threshold 53 and S1-exit 59) rapid-cycles the gas valve.
    // Post: latch holds state through the band.
    auto sp = default_setpoints();
    sp.temp_low = 58.0f;
    sp.dH2 = 5.0f;
    sp.heat_hysteresis = 1.0f;  // S1 exit = 59°F
    auto s = initial_state();
    // Latch sets at 52°F.
    determine_mode(make_inputs(52.0f, 0.9f), sp, s, 5000);
    ASSERT_TRUE(s.heat2_latched);
    // Temp recovers into the hysteresis band — latch holds.
    determine_mode(make_inputs(55.0f, 0.9f), sp, s, 5000);
    ASSERT_TRUE(s.heat2_latched);
    determine_mode(make_inputs(58.5f, 0.9f), sp, s, 5000);
    ASSERT_TRUE(s.heat2_latched);
    // Temp crosses S1 exit — latch releases.
    determine_mode(make_inputs(59.0f, 0.9f), sp, s, 5000);
    ASSERT_FALSE(s.heat2_latched);
    PASS();
}

TEST(s9_heat2_latch_does_not_re_set_in_hysteresis_band) {
    // After release, mild undershoot into the band should NOT re-latch.
    // Only a drop below S2 threshold re-latches.
    auto sp = default_setpoints();
    sp.temp_low = 58.0f;
    sp.dH2 = 5.0f;
    sp.heat_hysteresis = 1.0f;
    auto s = initial_state();
    s.heat2_latched = false;
    determine_mode(make_inputs(55.0f, 0.9f), sp, s, 5000);  // in the band
    ASSERT_FALSE(s.heat2_latched);
    determine_mode(make_inputs(53.5f, 0.9f), sp, s, 5000);  // still in band
    ASSERT_FALSE(s.heat2_latched);
    determine_mode(make_inputs(52.0f, 0.9f), sp, s, 5000);  // below threshold
    ASSERT_TRUE(s.heat2_latched);
    PASS();
}

TEST(s9_validate_swaps_inverted_vpd_bounds) {
    Setpoints sp = default_setpoints();
    // Operator typo: swapped low and high.
    sp.vpd_low = 1.5f;
    sp.vpd_high = 0.5f;
    validate_setpoints(sp);
    ASSERT_TRUE(sp.vpd_low < sp.vpd_high);
    // Individual clamps kept vpd_high inside [0.3, 5.0] and pulled
    // vpd_low below it.
    ASSERT_TRUE(sp.vpd_high >= 0.3f && sp.vpd_high <= 5.0f);
    ASSERT_TRUE(sp.vpd_low >= 0.1f);
    PASS();
}

TEST(s9_validate_enforces_vpd_ordering_across_all_four) {
    Setpoints sp = default_setpoints();
    // vpd_min_safe and vpd_max_safe were unclamped pre-sprint-9.
    sp.vpd_min_safe = 2.0f;   // nonsense: above vpd_low (0.5)
    sp.vpd_max_safe = 0.5f;   // nonsense: below vpd_high (1.2)
    validate_setpoints(sp);
    ASSERT_TRUE(sp.vpd_min_safe < sp.vpd_low);
    ASSERT_TRUE(sp.vpd_low < sp.vpd_high);
    ASSERT_TRUE(sp.vpd_high < sp.vpd_max_safe);
    PASS();
}

TEST(s9_validate_enforces_safety_gt_thigh_plus_dc2) {
    Setpoints sp = default_setpoints();
    sp.temp_high = 82.0f;
    sp.dC2 = 15.0f;          // 82 + 15 = 97, above safety_max 95
    sp.safety_max = 95.0f;
    validate_setpoints(sp);
    ASSERT_TRUE(sp.temp_high + sp.dC2 < sp.safety_max);
    PASS();
}

TEST(s9_validate_fixes_zero_width_fog_window) {
    Setpoints sp = default_setpoints();
    sp.fog_window_start = 12;
    sp.fog_window_end = 12;  // zero width
    validate_setpoints(sp);
    ASSERT_TRUE(sp.fog_window_start != sp.fog_window_end);
    PASS();
}

TEST(s9_validate_prevents_relief_longer_than_sealed) {
    Setpoints sp = default_setpoints();
    sp.sealed_max_ms = 100000;
    sp.relief_duration_ms = 200000;  // longer than sealed window
    validate_setpoints(sp);
    ASSERT_TRUE(sp.relief_duration_ms < sp.sealed_max_ms);
    PASS();
}

TEST(s9_validate_preserves_valid_input) {
    Setpoints sp = default_setpoints();
    Setpoints before = sp;
    validate_setpoints(sp);
    // Sensible defaults should survive unchanged for all the core fields.
    ASSERT_EQ(sp.temp_high, before.temp_high);
    ASSERT_EQ(sp.temp_low,  before.temp_low);
    ASSERT_EQ(sp.vpd_high,  before.vpd_high);
    ASSERT_EQ(sp.vpd_low,   before.vpd_low);
    ASSERT_EQ(sp.safety_max, before.safety_max);
    ASSERT_EQ(sp.safety_min, before.safety_min);
    ASSERT_EQ(sp.fog_window_start, before.fog_window_start);
    ASSERT_EQ(sp.fog_window_end, before.fog_window_end);
    PASS();
}

// ═══════════════════════════════════════════════════════════════════
// Sprint-10 — THERMAL_RELIEF both fans + vpd_min_safe SEALED exit +
// tunable magic numbers + day/night setpoint pairs
// ═══════════════════════════════════════════════════════════════════

TEST(s10_thermal_relief_runs_both_fans) {
    auto sp = default_setpoints();
    auto s = initial_state();
    auto out_lead1 = resolve_equipment(THERMAL_RELIEF, make_inputs(80.0f, 1.5f), sp, s, /*lead=*/true);
    ASSERT_TRUE(out_lead1.vent);
    ASSERT_TRUE(out_lead1.fan1);
    ASSERT_TRUE(out_lead1.fan2);  // sprint-10: no longer lead-only
    auto out_lead2 = resolve_equipment(THERMAL_RELIEF, make_inputs(80.0f, 1.5f), sp, s, /*lead=*/false);
    ASSERT_TRUE(out_lead2.vent);
    ASSERT_TRUE(out_lead2.fan1);
    ASSERT_TRUE(out_lead2.fan2);
    PASS();
}

TEST(s10_vpd_min_safe_breaks_sealed_mist_with_cleanup) {
    // Pre-sprint-10: vpd_min_safe only overrode mode==IDLE. A sticky
    // SEALED_MIST could drive VPD below vpd_min_safe with no exit.
    auto sp = default_setpoints();
    sp.econ_block = false;
    auto s = initial_state();
    s.mode_prev = SEALED_MIST;
    s.mist_stage = MIST_FOG;
    s.sealed_timer_ms = 200000;
    s.vpd_watch_timer_ms = 60000;
    s.mist_stage_timer_ms = 30000;
    // VPD dangerously low while sealed
    auto in = make_inputs(72.0f, sp.vpd_min_safe - 0.05f);
    Mode m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, DEHUM_VENT);
    // Seal-state cleanup: matches the was_sealed exit path.
    ASSERT_EQ(s.sealed_timer_ms, 0u);
    ASSERT_EQ(s.vpd_watch_timer_ms, 0u);
    ASSERT_EQ(s.mist_stage, MIST_WATCH);
    ASSERT_EQ(s.mist_stage_timer_ms, 0u);
    PASS();
}

TEST(s10_vpd_min_safe_override_respects_econ_block) {
    // With econ_block=true, the vpd_min_safe override does not force
    // DEHUM_VENT. Trace: the was_sealed branch exits SEALED_MIST to
    // IDLE because vpd_below_exit is trivially true at vpd_min_safe,
    // then the override sees mode=IDLE + econ_block=true and stays
    // in IDLE rather than flipping to DEHUM_VENT. Net: with econ
    // blocking the greenhouse lets the humidity sit — the P3#15
    // policy item still applies, this test just documents the
    // current econ-vs-safe precedence.
    auto sp = default_setpoints();
    sp.econ_block = true;
    auto s = initial_state();
    s.mode_prev = SEALED_MIST;
    s.mist_stage = MIST_S1;
    s.sealed_timer_ms = 100000;
    s.vpd_watch_timer_ms = 60000;
    auto in = make_inputs(72.0f, sp.vpd_min_safe - 0.05f);
    Mode m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, IDLE);  // was_sealed exited; econ_block prevents DEHUM_VENT
    PASS();
}

TEST(s10_vent_latch_timeout_is_tunable) {
    // Verify the ex-magic-number behaves as a Setpoints field.
    auto sp = default_setpoints();
    sp.vent_latch_timeout_ms = 120000;  // shorten to 2 min for test
    sp.max_relief_cycles = 3;
    auto s = initial_state();
    s.relief_cycle_count = 3;
    s.vpd_watch_timer_ms = 60000;
    auto in = make_inputs(72.0f, 1.5f);
    // Accumulate enough to trip the timeout
    determine_mode(in, sp, s, 60000);
    determine_mode(in, sp, s, 60000);
    Mode m = determine_mode(in, sp, s, 5000);
    // After ≥120 s of VENTILATE-latch, cycle count should reset.
    ASSERT_EQ(s.relief_cycle_count, 0u);
    ASSERT_EQ(s.vent_latch_timer_ms, 0u);
    PASS();
}

TEST(s10_econ_heat_margin_is_tunable) {
    auto sp = default_setpoints();
    sp.econ_block = true;
    sp.econ_heat_margin_f = 2.0f;  // tighter than the 5.0 default
    sp.temp_high = 80.0f;
    auto s = initial_state();
    // Temp at 79 (within old 5°F margin but outside new 2°F margin)
    // Old behavior: heat1 on. New: heat1 off.
    auto in = make_inputs(79.0f, 0.2f);
    auto out = resolve_equipment(IDLE, in, sp, s, true);
    ASSERT_FALSE(out.heat1);
    // Temp at 77 — still inside the tightened 2°F margin (80-2=78), so
    // the condition `temp_f < Thigh - margin` = 77 < 78 = true → heat
    in = make_inputs(77.0f, 0.2f);
    out = resolve_equipment(IDLE, in, sp, s, true);
    ASSERT_TRUE(out.heat1);
    PASS();
}

TEST(s10_day_night_uses_day_values_when_photoperiod_true) {
    auto sp = default_setpoints();
    sp.temp_high_day = 78.0f;
    sp.temp_high_night = 68.0f;
    sp.vpd_high_day = 1.2f;
    sp.vpd_high_night = 0.9f;
    auto s = initial_state();
    auto in = make_inputs(75.0f, 1.0f);
    in.is_photoperiod = true;
    Mode m = determine_mode(in, sp, s, 5000);
    // At 75°F with day temp_high=78: not cooling. VPD 1.0 < day high 1.2 → in band.
    ASSERT_EQ(m, IDLE);
    // Now 76°F with VPD 1.3 (above day high 1.2) — seal dwell accumulates.
    in = make_inputs(76.0f, 1.3f);
    in.is_photoperiod = true;
    determine_mode(in, sp, s, 60000);
    ASSERT_TRUE(s.vpd_watch_timer_ms > 0u);
    PASS();
}

TEST(s10_day_night_uses_night_values_when_photoperiod_false) {
    auto sp = default_setpoints();
    sp.temp_high_day = 78.0f;
    sp.temp_high_night = 68.0f;
    sp.vpd_high_day = 1.2f;
    sp.vpd_high_night = 0.9f;
    auto s = initial_state();
    // At 72°F (above night high 68): should trigger cooling even though
    // 72 is comfortably below the day high.
    auto in = make_inputs(72.0f, 0.8f);
    in.is_photoperiod = false;
    Mode m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, VENTILATE);  // 72 > 68 + bias_cool=0 → cooling
    PASS();
}

TEST(s10_day_night_falls_back_to_legacy_when_unset) {
    // resolve_active_band falls back to sp.temp_high etc. if the day/night
    // field is 0 (unset). Exercise by zeroing the day fields and relying on
    // legacy temp_high.
    auto sp = default_setpoints();
    sp.temp_high = 82.0f;
    sp.temp_high_day = 0.0f;   // force fallback
    sp.temp_high_night = 0.0f;
    auto in = make_inputs(84.0f, 0.9f);
    auto s = initial_state();
    Mode m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, VENTILATE);  // uses legacy temp_high=82, 84 > 82
    PASS();
}

TEST(s10_photoperiod_swap_activates_different_thresholds) {
    // Same sensor inputs, swap the flag — behavior changes.
    auto sp = default_setpoints();
    sp.temp_high_day = 80.0f;
    sp.temp_high_night = 68.0f;
    auto in = make_inputs(72.0f, 0.9f);  // between the two highs

    auto s_day = initial_state();
    in.is_photoperiod = true;
    Mode m_day = determine_mode(in, sp, s_day, 5000);
    ASSERT_EQ(m_day, IDLE);  // 72 < day high 80

    auto s_night = initial_state();
    in.is_photoperiod = false;
    Mode m_night = determine_mode(in, sp, s_night, 5000);
    ASSERT_EQ(m_night, VENTILATE);  // 72 > night high 68
    PASS();
}

TEST(s10_validate_backfills_day_night_from_legacy) {
    Setpoints sp = default_setpoints();
    sp.temp_high = 85.0f;
    sp.temp_high_day = 0.0f;
    sp.temp_high_night = 0.0f;
    sp.vpd_high = 1.4f;
    sp.vpd_high_day = 0.0f;
    sp.vpd_high_night = 0.0f;
    validate_setpoints(sp);
    ASSERT_EQ(sp.temp_high_day, 85.0f);
    ASSERT_EQ(sp.temp_high_night, 85.0f);
    ASSERT_EQ(sp.vpd_high_day, 1.4f);
    ASSERT_EQ(sp.vpd_high_night, 1.4f);
    PASS();
}

TEST(s10_validate_enforces_day_night_pair_ordering) {
    Setpoints sp = default_setpoints();
    // Inverted within the day pair
    sp.temp_high_day = 70.0f;
    sp.temp_low_day = 75.0f;
    // Inverted within the night pair
    sp.vpd_high_night = 0.5f;
    sp.vpd_low_night = 0.8f;
    validate_setpoints(sp);
    ASSERT_TRUE(sp.temp_low_day < sp.temp_high_day);
    ASSERT_TRUE(sp.vpd_low_night < sp.vpd_high_night);
    PASS();
}

TEST(s9_safety_heat_runs_lead_fan_for_circulation) {
    auto sp = default_setpoints();
    auto s = initial_state();
    auto in = make_inputs(40.0f, 0.3f);  // trips safety_heat
    Mode m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, SAFETY_HEAT);
    // Lead fan 1
    auto out1 = resolve_equipment(SAFETY_HEAT, in, sp, s, /*lead_is_fan1=*/true);
    ASSERT_TRUE(out1.heat1);
    ASSERT_TRUE(out1.heat2);
    ASSERT_TRUE(out1.fan1);
    ASSERT_FALSE(out1.fan2);
    ASSERT_FALSE(out1.vent);
    // Lead fan 2
    auto out2 = resolve_equipment(SAFETY_HEAT, in, sp, s, /*lead_is_fan1=*/false);
    ASSERT_FALSE(out2.fan1);
    ASSERT_TRUE(out2.fan2);
    ASSERT_FALSE(out2.vent);
    PASS();
}

TEST(s8_safety_heat_clears_same_timers_as_safety_cool) {
    // Pre-sprint-8: SAFETY_HEAT left relief_timer_ms, vent_latch_timer_ms,
    // and vpd_watch_timer_ms populated with whatever they held pre-safety.
    auto sp = default_setpoints();
    auto s = initial_state();
    s.sealed_timer_ms     = 100000;
    s.relief_timer_ms     = 50000;
    s.vpd_watch_timer_ms  = 60000;
    s.relief_cycle_count  = 2;
    s.vent_latch_timer_ms = 200000;
    auto in = make_inputs(40.0f, 0.3f);  // trips safety_heat
    Mode m = determine_mode(in, sp, s, 5000);
    ASSERT_EQ(m, SAFETY_HEAT);
    ASSERT_EQ(s.sealed_timer_ms, 0u);
    ASSERT_EQ(s.relief_timer_ms, 0u);
    ASSERT_EQ(s.vpd_watch_timer_ms, 0u);
    ASSERT_EQ(s.relief_cycle_count, 0u);
    ASSERT_EQ(s.vent_latch_timer_ms, 0u);
    PASS();
}

int main() {
    printf("═══════════════════════════════════════════════════════\n");
    printf("  Greenhouse Logic Tests — 11-fix review synthesis + OBS-1e\n");
    printf("  Same code as ESP32 firmware\n");
    printf("═══════════════════════════════════════════════════════\n\n");

    for (auto& t : test_registry) {
        printf("  %-50s ", t.name);
        int before = tests_failed;
        t.fn();
        if (tests_failed == before) printf("✓\n");
    }

    printf("\n═══════════════════════════════════════════════════════\n");
    printf("  %d passed, %d failed\n", tests_passed, tests_failed);
    printf("═══════════════════════════════════════════════════════\n");
    return tests_failed > 0 ? 1 : 0;
}
