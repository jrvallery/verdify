/*
 * test_greenhouse_logic.cpp — Native x86 tests for greenhouse controller logic.
 *
 * Compiles and runs the EXACT SAME greenhouse_logic.h that runs on the ESP32.
 * No mocks, no stubs — same code, same behavior.
 *
 * Compile: g++ -std=c++17 -I../lib -o test_greenhouse test_greenhouse_logic.cpp && ./test_greenhouse
 */

#include "greenhouse_logic.h"
#include <cstdio>
#include <cstring>
#include <cassert>
#include <vector>

// ── Test infrastructure ──────────────────────────────────────────────

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST(name) \
    static void test_##name(); \
    static struct Register_##name { \
        Register_##name() { test_registry.push_back({#name, test_##name}); } \
    } reg_##name; \
    static void test_##name()

#define ASSERT_EQ(a, b) do { \
    if ((a) != (b)) { \
        printf("  FAIL: %s != %s (line %d)\n", #a, #b, __LINE__); \
        tests_failed++; return; \
    } \
} while(0)

#define ASSERT_TRUE(x) do { \
    if (!(x)) { \
        printf("  FAIL: %s (line %d)\n", #x, __LINE__); \
        tests_failed++; return; \
    } \
} while(0)

#define ASSERT_FALSE(x) ASSERT_TRUE(!(x))

#define PASS() tests_passed++

struct TestEntry { const char* name; void (*fn)(); };
static std::vector<TestEntry> test_registry;

// ── Helpers ──────────────────────────────────────────────────────────

static SensorInputs make_inputs(float temp, float vpd, float rh = 60.0f) {
    return {
        .temp_f = temp, .vpd_kpa = vpd, .rh_pct = rh,
        .dew_point_f = temp - 10.0f, .outdoor_rh_pct = 30.0f,
        .enthalpy_delta = -5.0f,
        .vpd_south = vpd, .vpd_west = vpd, .vpd_east = vpd,
        .local_hour = 12, .occupied = false,
        .mister_state = 0, .humid_s2_duration_ms = 0
    };
}

// ═══════════════════════════════════════════════════════════════════════
// MODE DETERMINATION TESTS
// ═══════════════════════════════════════════════════════════════════════

TEST(idle_when_in_band) {
    auto in = make_inputs(72.0f, 0.9f);
    auto sp = default_setpoints();
    auto state = initial_state();
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, IDLE);
    PASS();
}

TEST(ventilate_when_hot) {
    auto in = make_inputs(84.0f, 0.9f);
    auto sp = default_setpoints();
    auto state = initial_state();
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, VENTILATE);
    PASS();
}

TEST(sealed_mist_after_dwell) {
    auto in = make_inputs(72.0f, 1.5f);
    auto sp = default_setpoints();
    auto state = initial_state();
    state.vpd_watch_timer_ms = 60000;  // dwell complete
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, SEALED_MIST);
    PASS();
}

TEST(sealed_mist_not_before_dwell) {
    auto in = make_inputs(72.0f, 1.5f);
    auto sp = default_setpoints();
    auto state = initial_state();
    state.vpd_watch_timer_ms = 30000;  // dwell NOT complete
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, IDLE);  // still watching, not sealed
    PASS();
}

TEST(safety_cool_at_max) {
    auto in = make_inputs(96.0f, 2.0f);
    auto sp = default_setpoints();
    auto state = initial_state();
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, SAFETY_COOL);
    PASS();
}

TEST(safety_heat_at_min) {
    auto in = make_inputs(44.0f, 0.3f);
    auto sp = default_setpoints();
    auto state = initial_state();
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, SAFETY_HEAT);
    PASS();
}

TEST(thermal_relief_after_sealed_max) {
    auto in = make_inputs(72.0f, 1.5f);
    auto sp = default_setpoints();
    auto state = initial_state();
    state.mode_prev = SEALED_MIST;
    state.sealed_timer_ms = 600000;  // max sealed time
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, THERMAL_RELIEF);
    PASS();
}

TEST(relief_returns_to_sealed_if_vpd_high) {
    auto in = make_inputs(72.0f, 1.5f);
    auto sp = default_setpoints();
    auto state = initial_state();
    state.mode_prev = THERMAL_RELIEF;
    state.relief_timer_ms = 90000;  // relief duration expired
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, SEALED_MIST);
    PASS();
}

TEST(relief_returns_to_idle_if_vpd_resolved) {
    auto in = make_inputs(72.0f, 0.8f);
    auto sp = default_setpoints();
    auto state = initial_state();
    state.mode_prev = THERMAL_RELIEF;
    state.relief_timer_ms = 90000;
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, IDLE);
    PASS();
}

TEST(sealed_exits_to_idle_when_vpd_resolves) {
    auto in = make_inputs(72.0f, 0.85f);  // below vpd_high - hysteresis (1.2-0.3=0.9)
    auto sp = default_setpoints();
    auto state = initial_state();
    state.mode_prev = SEALED_MIST;
    state.sealed_timer_ms = 300000;
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, IDLE);
    PASS();
}

TEST(sealed_exits_to_ventilate_when_vpd_resolves_but_hot) {
    auto in = make_inputs(84.0f, 0.85f);
    auto sp = default_setpoints();
    auto state = initial_state();
    state.mode_prev = SEALED_MIST;
    state.sealed_timer_ms = 300000;
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, VENTILATE);
    PASS();
}

TEST(dehum_vent_when_vpd_too_low) {
    auto in = make_inputs(72.0f, 0.15f);
    auto sp = default_setpoints();
    auto state = initial_state();
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, DEHUM_VENT);
    PASS();
}

TEST(dehum_blocked_by_economiser) {
    auto in = make_inputs(72.0f, 0.15f);
    auto sp = default_setpoints();
    sp.econ_block = true;
    auto state = initial_state();
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, IDLE);  // can't vent, stay idle
    PASS();
}

TEST(bias_cool_prevents_ventilate) {
    auto in = make_inputs(80.0f, 0.9f);
    auto sp = default_setpoints();
    sp.temp_high = 78.0f;
    sp.bias_cool = 3.0f;  // effective Thigh = 81
    auto state = initial_state();
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, IDLE);  // 80 < 81, no cooling
    PASS();
}

TEST(without_bias_cool_ventilates) {
    auto in = make_inputs(80.0f, 0.9f);
    auto sp = default_setpoints();
    sp.temp_high = 78.0f;
    sp.bias_cool = 0.0f;  // effective Thigh = 78
    auto state = initial_state();
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, VENTILATE);
    PASS();
}

TEST(vpd_extreme_bypasses_dwell) {
    auto in = make_inputs(72.0f, 3.5f);  // > vpd_max_safe (3.0)
    auto sp = default_setpoints();
    auto state = initial_state();
    // No dwell timer set — should bypass
    Mode m = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m, SEALED_MIST);
    PASS();
}

// ═══════════════════════════════════════════════════════════════════════
// EQUIPMENT RESOLUTION TESTS
// ═══════════════════════════════════════════════════════════════════════

TEST(idle_equipment_all_off) {
    auto in = make_inputs(72.0f, 0.9f);
    auto sp = default_setpoints();
    auto out = resolve_equipment(IDLE, in, sp, true);
    ASSERT_FALSE(out.vent); ASSERT_FALSE(out.fan1); ASSERT_FALSE(out.fan2);
    ASSERT_FALSE(out.heat1); ASSERT_FALSE(out.heat2); ASSERT_FALSE(out.fog);
    PASS();
}

TEST(idle_with_heating) {
    auto in = make_inputs(56.0f, 0.9f);  // below temp_low (58)
    auto sp = default_setpoints();
    auto out = resolve_equipment(IDLE, in, sp, true);
    ASSERT_FALSE(out.vent); ASSERT_FALSE(out.fan1);
    ASSERT_TRUE(out.heat1); ASSERT_TRUE(out.heat2);
    PASS();
}

TEST(ventilate_opens_vent_and_fans) {
    auto in = make_inputs(84.0f, 0.9f);
    auto sp = default_setpoints();
    auto out = resolve_equipment(VENTILATE, in, sp, true);
    ASSERT_TRUE(out.vent); ASSERT_TRUE(out.fan1);
    ASSERT_FALSE(out.heat1); ASSERT_FALSE(out.fog);
    PASS();
}

TEST(sealed_mist_vent_closed_fans_off) {
    auto in = make_inputs(72.0f, 1.5f);
    auto sp = default_setpoints();
    auto out = resolve_equipment(SEALED_MIST, in, sp, true);
    ASSERT_FALSE(out.vent); ASSERT_FALSE(out.fan1); ASSERT_FALSE(out.fan2);
    PASS();
}

TEST(thermal_relief_opens_vent) {
    auto in = make_inputs(72.0f, 1.5f);
    auto sp = default_setpoints();
    auto out = resolve_equipment(THERMAL_RELIEF, in, sp, true);
    ASSERT_TRUE(out.vent); ASSERT_TRUE(out.fan1);
    ASSERT_FALSE(out.heat1); ASSERT_FALSE(out.fog);
    PASS();
}

TEST(safety_cool_all_fans_open) {
    auto in = make_inputs(96.0f, 2.0f);
    auto sp = default_setpoints();
    auto out = resolve_equipment(SAFETY_COOL, in, sp, true);
    ASSERT_TRUE(out.vent); ASSERT_TRUE(out.fan1); ASSERT_TRUE(out.fan2);
    ASSERT_FALSE(out.heat1); ASSERT_FALSE(out.heat2);
    PASS();
}

TEST(safety_heat_both_heaters_vent_closed) {
    auto in = make_inputs(44.0f, 0.3f);
    auto sp = default_setpoints();
    auto out = resolve_equipment(SAFETY_HEAT, in, sp, true);
    ASSERT_FALSE(out.vent); ASSERT_FALSE(out.fan1);
    ASSERT_TRUE(out.heat1); ASSERT_TRUE(out.heat2);
    PASS();
}

// ═══════════════════════════════════════════════════════════════════════
// INVARIANT TESTS — exhaustive sweep
// ═══════════════════════════════════════════════════════════════════════

TEST(no_open_vent_misting_ever) {
    auto sp = default_setpoints();
    int violations = 0;
    for (float t = 40; t <= 100; t += 2) {
        for (float v = 0.1f; v <= 3.5f; v += 0.1f) {
            auto in = make_inputs(t, v);
            auto state = initial_state();
            state.vpd_watch_timer_ms = 60000;  // dwell complete
            Mode m = determine_mode(in, sp, state, 5000);
            auto out = resolve_equipment(m, in, sp, true);
            if (m == SEALED_MIST && out.vent) violations++;
            if (m == SEALED_MIST && (out.fan1 || out.fan2)) violations++;
        }
    }
    ASSERT_EQ(violations, 0);
    PASS();
}

TEST(no_heater_with_vent_open) {
    auto sp = default_setpoints();
    int violations = 0;
    for (float t = 40; t <= 100; t += 2) {
        for (float v = 0.1f; v <= 3.5f; v += 0.1f) {
            auto in = make_inputs(t, v);
            auto state = initial_state();
            state.vpd_watch_timer_ms = 60000;
            Mode m = determine_mode(in, sp, state, 5000);
            auto out = resolve_equipment(m, in, sp, true);
            if (out.vent && (out.heat1 || out.heat2)) violations++;
        }
    }
    ASSERT_EQ(violations, 0);
    PASS();
}

TEST(no_fans_without_vent) {
    auto sp = default_setpoints();
    int violations = 0;
    for (float t = 40; t <= 100; t += 2) {
        for (float v = 0.1f; v <= 3.5f; v += 0.1f) {
            auto in = make_inputs(t, v);
            auto state = initial_state();
            state.vpd_watch_timer_ms = 60000;
            Mode m = determine_mode(in, sp, state, 5000);
            auto out = resolve_equipment(m, in, sp, true);
            if (!out.vent && (out.fan1 || out.fan2)) violations++;
        }
    }
    ASSERT_EQ(violations, 0);
    PASS();
}

// ═══════════════════════════════════════════════════════════════════════
// SCENARIO: Cold night with heater cycling
// ═══════════════════════════════════════════════════════════════════════

TEST(cold_night_no_vent_oscillation) {
    auto sp = default_setpoints();
    sp.temp_high = 78.0f; sp.temp_low = 62.0f;
    sp.bias_cool = 3.0f;  // Thigh = 81
    auto state = initial_state();

    float temps[] = {60,62,64,66,68,70,72,74,76,78,80,79,78,76,74,72,70,68,66,64,62,60};
    int vent_opens = 0;

    for (float t : temps) {
        auto in = make_inputs(t, 0.6f + (t-60)*0.02f);
        Mode m = determine_mode(in, sp, state, 5000);
        auto out = resolve_equipment(m, in, sp, true);
        if (out.vent) vent_opens++;
    }
    ASSERT_EQ(vent_opens, 0);
    PASS();
}

// ═══════════════════════════════════════════════════════════════════════
// SCENARIO: Hot dry day sealed mist cycle
// ═══════════════════════════════════════════════════════════════════════

TEST(hot_dry_day_sealed_cycle) {
    auto sp = default_setpoints();
    sp.temp_high = 78.0f; sp.vpd_high = 1.2f;
    auto state = initial_state();

    // Warm up to above band
    auto in1 = make_inputs(80.0f, 1.3f);
    // Run 12 cycles (60s) of VPD watch
    for (int i = 0; i < 12; i++) {
        determine_mode(in1, sp, state, 5000);
    }
    // Should now be SEALED_MIST
    Mode m = determine_mode(in1, sp, state, 5000);
    ASSERT_EQ(m, SEALED_MIST);

    // Verify: vent closed, fans off during seal
    auto out = resolve_equipment(m, in1, sp, true);
    ASSERT_FALSE(out.vent);
    ASSERT_FALSE(out.fan1);
    ASSERT_FALSE(out.fan2);

    // Simulate sealed for 600s → thermal relief
    state.sealed_timer_ms = 600000;
    m = determine_mode(in1, sp, state, 5000);
    ASSERT_EQ(m, THERMAL_RELIEF);

    // Verify: vent open during relief
    out = resolve_equipment(m, in1, sp, true);
    ASSERT_TRUE(out.vent);

    PASS();
}

// ═══════════════════════════════════════════════════════════════════════
// BUG REGRESSION TESTS (from external review, 2026-04-11)
// ═══════════════════════════════════════════════════════════════════════

TEST(bug1_mode_prev_reads_last_cycle) {
    // Bug 1: mode_prev must reflect LAST cycle, not current
    auto in = make_inputs(72.0f, 1.3f);
    auto sp = default_setpoints();
    auto state = initial_state();
    // Cycle 1: VPD above band, dwell complete → enters SEALED_MIST
    state.vpd_watch_timer_ms = 60000;
    Mode m1 = determine_mode(in, sp, state, 5000);
    ASSERT_EQ(m1, SEALED_MIST);
    // Cycle 2: VPD drops below exit → should exit to IDLE
    // This requires mode_prev == SEALED_MIST (from cycle 1)
    auto in2 = make_inputs(72.0f, 0.85f);  // below vpd_high - hysteresis
    Mode m2 = determine_mode(in2, sp, state, 5000);
    ASSERT_EQ(m2, IDLE);
    PASS();
}

TEST(bug3_vpd_safety_cannot_override_safety_heat) {
    // Bug 3: VPD > vpd_max_safe must NOT override SAFETY_HEAT
    auto in = make_inputs(40.0f, 3.5f);  // freezing + extreme dry VPD
    auto sp = default_setpoints();
    auto state = initial_state();
    Mode m = determine_mode(in, sp, state, 5000);
    // Must be SAFETY_HEAT (temp takes priority), not SEALED_MIST
    ASSERT_EQ(m, SAFETY_HEAT);
    PASS();
}

TEST(bug4_dehum_vent_has_hysteresis) {
    // Bug 4: DEHUM_VENT should stay until VPD rises to vpd_low (not exit immediately)
    auto sp = default_setpoints();
    auto state = initial_state();
    // Enter DEHUM_VENT
    auto in1 = make_inputs(72.0f, 0.15f);  // below vpd_low - hysteresis (0.5 - 0.3 = 0.2)
    Mode m1 = determine_mode(in1, sp, state, 5000);
    ASSERT_EQ(m1, DEHUM_VENT);
    // VPD rises to 0.3 (still below vpd_low 0.5) → should STAY in DEHUM_VENT
    auto in2 = make_inputs(72.0f, 0.3f);
    Mode m2 = determine_mode(in2, sp, state, 5000);
    ASSERT_EQ(m2, DEHUM_VENT);
    // VPD rises to 0.5 (at vpd_low) → should exit to IDLE
    auto in3 = make_inputs(72.0f, 0.5f);
    Mode m3 = determine_mode(in3, sp, state, 5000);
    ASSERT_EQ(m3, IDLE);
    PASS();
}

TEST(gap_ventilate_has_temp_hysteresis) {
    // VENTILATE should not exit until temp drops below Thigh - temp_hysteresis
    auto sp = default_setpoints();
    sp.temp_high = 78.0f;
    sp.temp_hysteresis = 1.0f;  // exit at 77°F, not 78°F
    auto state = initial_state();
    // Enter VENTILATE at 79°F
    auto in1 = make_inputs(79.0f, 0.9f);
    Mode m1 = determine_mode(in1, sp, state, 5000);
    ASSERT_EQ(m1, VENTILATE);
    // Drop to 77.5°F (still above Thigh - hysteresis = 77°F) → stay VENTILATE
    auto in2 = make_inputs(77.5f, 0.9f);
    Mode m2 = determine_mode(in2, sp, state, 5000);
    ASSERT_EQ(m2, VENTILATE);
    // Drop to 76.9°F (below 77°F) → exit to IDLE
    auto in3 = make_inputs(76.9f, 0.9f);
    Mode m3 = determine_mode(in3, sp, state, 5000);
    ASSERT_EQ(m3, IDLE);
    PASS();
}

TEST(gap_relief_cycle_counter_tracks) {
    // Relief cycle counter should increment on consecutive sealed→relief cycles
    auto in = make_inputs(72.0f, 1.5f);
    auto sp = default_setpoints();
    auto state = initial_state();
    state.vpd_watch_timer_ms = 60000;
    // Enter sealed
    determine_mode(in, sp, state, 5000);
    // Run to relief
    state.sealed_timer_ms = 600000;
    determine_mode(in, sp, state, 5000);
    ASSERT_EQ(state.relief_cycle_count, 0u);  // not incremented until relief COMPLETES
    // Complete relief
    state.relief_timer_ms = 90000;
    determine_mode(in, sp, state, 5000);
    ASSERT_EQ(state.relief_cycle_count, 1u);  // incremented
    // Second cycle
    state.sealed_timer_ms = 600000;
    determine_mode(in, sp, state, 5000);
    state.relief_timer_ms = 90000;
    determine_mode(in, sp, state, 5000);
    ASSERT_EQ(state.relief_cycle_count, 2u);
    PASS();
}

TEST(bug6_idle_no_heater_for_vpd) {
    // Bug 6: IDLE should NOT fire heaters to raise VPD (oscillation risk)
    auto in = make_inputs(72.0f, 0.3f);  // VPD below vpd_low but temp is fine
    auto sp = default_setpoints();
    sp.econ_block = true;  // can't vent
    auto out = resolve_equipment(IDLE, in, sp, true);
    // Should NOT have heaters (temp 72 is well above Tlow 58+5=63)
    ASSERT_FALSE(out.heat1);
    ASSERT_FALSE(out.heat2);
    PASS();
}

// ═══════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════

int main() {
    printf("═══════════════════════════════════════════════════════\n");
    printf("  Greenhouse Logic Tests (native x86)\n");
    printf("  Same code as ESP32 firmware — greenhouse_logic.h\n");
    printf("═══════════════════════════════════════════════════════\n\n");

    for (auto& t : test_registry) {
        printf("  %-45s ", t.name);
        int before = tests_failed;
        t.fn();
        if (tests_failed == before) printf("✓\n");
    }

    printf("\n═══════════════════════════════════════════════════════\n");
    printf("  %d passed, %d failed\n", tests_passed, tests_failed);
    printf("═══════════════════════════════════════════════════════\n");

    return tests_failed > 0 ? 1 : 0;
}
