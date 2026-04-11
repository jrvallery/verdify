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
             .local_hour = 12, .occupied = false };
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
    auto sp = default_setpoints(); sp.temp_low = 58; sp.heat_hysteresis = 1.0;
    // Heat2 (gas) needs temp < Tlow - heat_hysteresis = 57°F
    auto out = equip(IDLE, 57.5, 0.9, sp);
    ASSERT_TRUE(out.heat1);   // electric yes (57.5 < 63)
    ASSERT_FALSE(out.heat2);  // gas no (57.5 > 57)
    auto out2 = equip(IDLE, 56.5, 0.9, sp);
    ASSERT_TRUE(out2.heat1);  // electric yes
    ASSERT_TRUE(out2.heat2);  // gas yes (56.5 < 57)
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
    auto out = equip(SENSOR_FAULT, 72, 0.9);
    ASSERT_TRUE(out.heat1);    // keep warm
    ASSERT_FALSE(out.heat2);   // no gas
    ASSERT_FALSE(out.vent);    // sealed
    ASSERT_FALSE(out.fan1);
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
    auto sp = default_setpoints(); int v = 0;
    for (float t = 40; t <= 100; t += 2)
        for (float vpd = 0.1f; vpd <= 3.5f; vpd += 0.1f) {
            auto s = initial_state(); s.vpd_watch_timer_ms = 60000;
            Mode m = determine_mode(make_inputs(t, vpd), sp, s, 5000);
            auto out = resolve_equipment(m, make_inputs(t, vpd), sp, s, true);
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

int main() {
    printf("═══════════════════════════════════════════════════════\n");
    printf("  Greenhouse Logic Tests — 11-fix review synthesis\n");
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
