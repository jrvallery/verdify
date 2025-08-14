Controller (FastAPI Template Aligned)

This section specifies the ESPHome based firmware that runs on Kincony A16S controllers. It defines hardware constraints, bootstrapping, configuration/plan handling, local control algorithms (staging, dehumidification by enthalpy, fan rotation), actuator timing guarantees, manual overrides, irrigation/fertilization/lighting job queues, fallback behavior, persistence, and telemetry. The intent is to make the firmware implementable and testable by human and agentic coders.

**FastAPI Template Integration**
* Controllers communicate exclusively via HTTP REST endpoints with `/api/v1` prefix
* Authentication uses DeviceToken scheme for all controller endpoints
* Configuration and plan updates use ETag-based conditional requests (304 Not Modified)
* All requests follow OpenAPI schema for automatic client generation
* Error responses follow FastAPI HTTPException format with structured ErrorResponse schema
* Telemetry data conforms to Pydantic models for type-safe validation
 
1) Hardware & Platform Constraints
-	Board: Kincony KC868 A16S (ESP32), 16 relay outputs, RS 485, Ethernet/Wi Fi.
-	Platform: ESPHome (ESP IDF). YAML config with small custom components (C++) where needed.
-	Relays: Driven via I²C PCF8574/8575 expanders (A16S uses expander chips behind the scenes).
-	Sensors:
o	Modbus RTU over RS 485 for temperature, humidity, CO₂, pressure, soil moisture, water flow, etc.
o	Optional analog/digital GPIOs for simple sensors (e.g., door, float).
-	Buttons (manual overrides): Three physical inputs (cool, heat, humid) on GPIO/ADC threshold; de bounce in firmware.
-	Clock: SNTP for UTC; tolerate temporary skew.
-	Storage: ESP32 NVS and LittleFS for config.json + plan.json (~50–200 KB).
-	Networking: DHCP IPv4; Wi Fi or Ethernet. **HTTPS ONLY** - all API calls MUST use TLS with valid certificates. HTTP connections MUST be rejected.

**Security Requirements:**
-	MUST use HTTPS for all API communications with valid TLS certificates
-	MUST reject HTTP connections and disable insecure protocols
-	MUST validate server certificates (verify_ssl=true)
-	MUST use secure headers (User-Agent, Authorization) 

Agentic checklist
-	MUST support 16 relays with min on/off timing guarantees.
-	MUST support Modbus sensor polling at configured intervals.
-	SHOULD auto recover from sensor timeouts (mark sensor offline, continue loop).
-	MUST persist config/plan to LittleFS and restore at boot.
-	MUST enforce HTTPS-only communication with API endpoints.
 
2) Identity, Boot & Provisioning
- device_name: Computed at flash/boot as verdify-<aabbcc> where <aabbcc> is the lowercase hex of the last 3 MAC bytes. Shown on captive portal and boot logs.
- claim_code: 6 digit numeric string (regex ^\d{6}$) generated on first boot; displayed in portal; stored in NVS (never transmitted after claim except for /hello retries).
- Boot flow (aligned with updated API where /hello returns status only and token delivery occurs when claimed):
  1. Bring up network, sync time.
  2. Display device_name and claim_code (captive portal / serial).
  3. POST /api/v1/hello (unauth) with { device_name, claim_code, firmware, hardware_profile, ts_utc } every 15 s (jitter) until status returns "claimed" (controller_id & greenhouse_id present).
  4. When status == claimed, immediately POST /api/v1/controllers/{controller_uuid}/token-exchange (unauth) with {device_name, claim_code} to obtain long-lived device_token + initial config/plan ETags.
  5. GET /api/v1/controllers/by-name/{device_name}/config (If-None-Match: previous ETag). Persist/apply if new.
  6. GET /api/v1/controllers/{controller_id}/plan (or /api/v1/controllers/me/plan) with ETag. Persist/apply if new.
- Strong ETags: expect patterns "config:v<version>:<sha8>" and "plan:v<version>:<sha8>".
Agentic checklist
- MUST compute device_name using ESPHome MAC suffix (6 hex, lowercase, hyphen).
- MUST retry /api/v1/hello with exponential backoff + jitter until claimed.
- MUST persist device_token securely (NVS) and never log it.
- SHOULD detect status transition pending→claimed and immediately attempt first config/plan fetch.
 
3) Configuration: Parse, Store, Apply
Source: API serves full config.json (see Configuration section). Controller treats config as authoritative and versioned.
Key config elements (enforced locally):
-	is_climate_controller (bool): Only one controller per greenhouse runs climate loop; others ignore staging rules.
-	Sensor map: sensor_id → {scope, kind, zone_id?, modbus_addr, reg, scale, offset, poll_interval_s, include_in_climate_loop}.
-	Actuator map: actuator_id → {kind, relay_channel, min_on_ms, min_off_ms, fail_safe_state, zone_id?}.
-	Fan groups: {fan_group_id → [actuator_id...]} and state_rules[].must_on_fan_groups[{fan_group_id, on_count}].
-	Buttons: {button_id → {pin/adc, mapped_stage, timeout_s}}.
-	Baselines & rails: greenhouse min/max temp °C, min/max VPD kPa, baseline thresholds, hysteresis, offsets.
-	Stage rules grid: For every (temp_stage ∈ [-3..+3], humi_stage ∈ [-3..+3]), lists of MUST_ON/MUST_OFF actuators, plus must_on_fan_groups and a fallback rule.
Apply order
1.	Validate schema signature/version.
2.	Build lookup maps by UUID.
3.	Initialize relay supervisors with min on/off and last change timestamps (restore from NVS).
4.	Initialize fan rotation state per group (restore from NVS).
5.	Mark climate role (enable/disable control loop automations).
Persistence
-	Write config.json to LittleFS; keep last 2 versions (rollback on parse/apply error).
-	Store critical run state in NVS: config_version, plan_version, relay last state/time, fan lead indices.
 
4) Plan: Parse, Store, Apply
Source: API plan endpoints return horizon (e.g., 10 days at 30 min steps).
Contents consumed by controller
-	Setpoints per time bucket: min_temp_c, max_temp_c, min_vpd_kpa, max_vpd_kpa, deltas, offsets, hysteresis for temp and humidity staging.
-	Irrigation: per zone {zone_id, ts, duration_s, min_soil_vwc?}.
-	Fertilization: per zone {zone_id, ts, duration_s}.
-	Lighting: per actuator {actuator_id, ts, duration_s}.
Persistence & size
-	10 days × 48 buckets/day × ~12 floats ≈ ~46–60 KB.
-	Store as compact JSON (no whitespace) in LittleFS /plan.json. Keep plan_version, effective_from/to.
Fallback
-	If no plan or current time not covered, fall back to baselines from config.json under greenhouse rails.
 
5) Local Measurements & Derived Values
- Interior averages (for climate loop): average only sensors with include_in_climate_loop=true AND scope ∈ {zone, greenhouse} for temperature & humidity (& pressure if interior sensor exists). Ignore scope=external for interior averages.
- Exterior values: sensors with scope=external (never mixed with interior).
- VPD (kPa): Standard formula from interior temp (°C) & RH (%) — canonical humidity control variable (RH stages deprecated in favor of VPD stages).
- Enthalpy (kJ/kg): Compute h_in, h_out from interior/exterior T/RH/pressure; delta = h_out - h_in. Negative delta (< 0) favors ventilation for dehumidification; positive delta favors heating + reduced ventilation.
**Derived calculations:**

> **Algorithm Reference**: For complete climate calculation functions, see [DATABASE.md - Climate Calculation Functions](./DATABASE.md#algorithms-functions).

**VPD & Enthalpy Functions:**
- `calc_vpd_kpa(temp_c, rh_pct)`: Vapor pressure deficit from temperature and humidity
- `calc_enthalpy_kjkg(temp_c, rh_pct, pressure_hpa)`: Moist air specific enthalpy for dehumidification decisions

**Stage Determination:**
- `stage_for_temp(temp_c, eff_min, eff_max, hyst)`: Temperature stage [-3..+3] with hysteresis
- `stage_for_humi(vpd_kpa, eff_min_vpd, eff_max_vpd, hyst_vpd)`: Humidity stage based on VPD
 
6) Stage Determination (±3)
Inputs each loop (every ~2–5 s): avg_interior_temp_c, avg_interior_rh_pct, avg_interior_pressure_hpa, avg_vpd_kpa, exterior_temp_c, exterior_rh_pct, exterior_pressure_hpa, baselines, plan deltas/offsets/hysteresis.
**Algorithm:**

> **Algorithm Reference**: For complete stage determination algorithms, see [DATABASE.md - Stage Determination Algorithms](./DATABASE.md#algorithms-functions).

1. Effective thresholds = baselines ⊕ plan deltas/offsets; clamp to greenhouse rails
2. Temperature stage ∈ [-3..+3] via hysteresis bands around effective min/max temp
3. Humidity stage (VPD-based) ∈ [-3..+3]: compare avg_vpd_kpa to effective min/max VPD with hysteresis
4. Enthalpy gate: when humi_stage < 0 (dehumidification required) use enthalpy delta to prefer ventilation vs heating path

**Stage Convention:**
- **Temperature**: Negative values = too cold (heating demand), positive = too hot (cooling demand)
- **Humidity**: Negative values = too humid (dehumidification demand), positive = too dry (humidification demand)
 
7) Applying Rules: MUST_ON/OFF, Fan Rotation, Min Timings
Inputs: temp_stage, humi_stage, state_rules[] from config, manual override (if active), enthalpy gate signal.
Rule lookup:
-	Fetch rule row where temp_stage and humi_stage match; else apply fallback.
Manual override:
-	If active (e.g., COOL_S1), force corresponding stages for the remaining timeout seconds; ignore plan driven changes.
Fan rotation:
-	must_on_fan_groups[{fan_group_id, on_count}].
-	Maintain lead index per group (restore_value: yes).
-	Rotate on transitions from on_count=0 → >0 (i.e., when fans become needed).
-	Turn ON lead + (on_count - 1) next members (wrap around). ALL other members in that group MUST be OFF unless explicitly listed in MUST_ON.
Enthalpy gate application (dehumid):
-	If humi_stage indicates dehumidification:
o	Ventilation path (delta < 0): favor turning ON fan/vent actuators, avoid heater unless required by temp stage.
o	Heating path (delta ≥ 0): allow heater (within rails) and limit fan/vent to minimum needed.
o	This is implemented by filtering the MUST_ON list per rule based on gate; see pseudo code.
Actuator timing guarantees:
-	Each actuator has min_on_ms and min_off_ms. A relay supervisor enforces:
o	Do not turn OFF before min_on_ms elapsed.
o	Do not turn ON before min_off_ms elapsed.
-	If rule requires change violating mins, queue the change until safe.
Pseudo code (apply rules):
def apply_rules(temp_stage, humi_stage, enthalpy_delta):
    rule = find_rule(temp_stage, humi_stage) or config.fallback_rule
    on_set  = set(rule.must_on_actuators)
    off_set = set(rule.must_off_actuators)

    # enthalpy gate filtering (example strategy)
    if humi_stage > 0:  # dehumid needed
        if enthalpy_delta < 0:
            # prefer ventilation, avoid heater unless temp_stage < 0
            off_set |= {a for a in on_set if actuator[a].kind == 'heater' and temp_stage >= 0}
        else:
            # prefer heating, reduce ventilation if temp_stage <= 0
            off_set |= {a for a in on_set if actuator[a].kind in {'fan','vent'} and temp_stage <= 0}

    # fan groups
    for fg in rule.must_on_fan_groups:
        members = fan_groups[fg.fan_group_id]
        n = min(fg.on_count, len(members))
        if n > 0 and last_on_count[fg.fan_group_id] == 0:
            lead_idx[fg.fan_group_id] = (lead_idx[fg.fan_group_id] + 1) % len(members)
        last_on_count[fg.fan_group_id] = n

        order = round_robin(members, start=lead_idx[fg.fan_group_id])
        on_members = set(order[:n])
        on_set |= on_members
        off_set |= (set(members) - on_members)

    # resolve conflicts: MUST_OFF wins unless specifically overridden by rails
    on_set -= off_set

    # apply with min on/off constraints
    for a in all_actuators:
        desired = a in on_set
        relay_supervisor_request(a, desired)
 
8) Manual Overrides (Physical Buttons)
-	Buttons: button_cool, button_heat, button_humid mapped in config to target stage (COOL_S1, HEAT_S1, HUMID_S1, etc.) and timeout_s.
-	On press: Set override.active=true, set override.target_stages and expires_at=now+timeout_s.
-	While active: Bypass stage computation; feed target stages to rule lookup.
-	On release: Keep override active until timeout (or config allows cancel on release).
-	Telemetry: Button events POSTed immediately (see Telemetry section).
Agentic checklist
-	MUST debounce (≥50 ms).
-	MUST enforce per button configurable timeout.
-	MUST reflect override in status telemetry (seconds remaining).
 
9) Job Queues: Irrigation, Fertilization, Lighting
-	Irrigation lockout: Only one irrigation valve (kind='irrigation_valve') ON at a time per controller.
-	Queueing: If overlapping schedules occur, enqueue FIFO. Start next immediately after previous completes and min_off satisfied.
-	Fertilization: If fertilizer valve exists, treat similarly; if both irrigation and fertilizer needed for same zone, run sequentially unless plan explicitly pairs them (MVP: sequential).
-	Lighting: Execute independent of irrigation lockout (MVP). (Power budget limitations are not enforced in MVP.)
Scheduler
-	Poll current UTC; for all plan jobs at/within small window (e.g., ±30 s), enqueue if not already enqueued.
-	Maintain per job state (pending → running → done).
-	Respect actuator min_on/off and rails.
Pseudo code (queue runner):
def scheduler_tick(now):
    # enqueue due jobs
    for job in plan.jobs_due(now):
        if not job.enqueued:
            q.enqueue(job); job.enqueued = True

    # irrigation lockout
    if not irrigation_busy():
        next_job = q.peek_first(lambda j: j.type == 'irrigation')
        if next_job:
            start_job(next_job)

    # fert & light
    for kind in ['fertilization','lighting']:
        if not job_running(kind):
            j = q.peek_first(lambda jj: jj.type == kind)
            if j: start_job(j)

def start_job(job):
    for aid in job.actuators_to_on():
        relay_supervisor_request(aid, True)
    job.started_at = now()

def job_tick():
    for job in running_jobs():
        if now() >= job.started_at + job.duration:
            for aid in job.actuators_to_on():
                relay_supervisor_request(aid, False)
            mark_done(job)
 
10) Fallback & Safety
-	Primary: Execute current plan while valid.
-	If plan window missing or expired: Use baselines (from config) + greenhouse guard rails.
-	On sensor failure: Exclude faulty sensor from averages; if no interior sensors remain, go to safe state using fallback rule (e.g., purge fans minimal).
-	On boot or network loss: Use last persisted config/plan; if none, default all relays OFF except those marked fail_safe_state='on'.
-	Rails always win: Never exceed min/max_temp_c and min/max_vpd_kpa.
 
11) Telemetry
Cadence (unchanged): sensors (10–15s), status (30s), actuator edges (immediate), inputs (button events immediate). Optional mixed batch endpoint consolidates payloads.
Identity: Ingestion authenticates via X-Device-Token header; controller_id & greenhouse_id are derived server-side. Payload MAY omit controller_id/device_name fields (they are ignored if supplied). This avoids spoofing/mismatch error classes.
Frames:
- Sensors: { device_ts_utc?, readings:[{sensor_id, value, ts_utc?}] }
- Actuator edges: { events:[{event_id, actuator_id, ts_utc, state, reason, meta?}] }
- Status: { ts_utc, interior{avg_temp_c,avg_rh_pct,avg_pressure_hpa,avg_vpd_kpa}, exterior{temp_c,rh_pct,pressure_hpa}, enthalpy{in_kjkg,out_kjkg,delta_kjkg}, stages{temp_stage,humi_stage}, override{active,source?,seconds_remaining?}, metrics{uptime_s,loop_ms,wifi_rssi_dbm?,heap_free_b?,irrigation_queue_depth?}, config_version, plan_version }
- Inputs: { events:[{event_id,button_id,ts_utc,action,mapped_stage?,timeout_s?}] }
Batch: { sensors?, actuators?, status?, inputs? } with same inner item shapes; gzip strongly recommended.
Agentic checklist
- MUST include Authorization header only (no controller_id fields required).
- MUST retry (exponential backoff) on ≥500; jitter to avoid thundering herd.
- MUST buffer bounded queue (≥256 events) when offline; drop oldest sensor frames first, never drop actuator edges.
 
12) YAML Stubs (ESPHome)
Note: Stubs illustrate structure; actual pins/addresses depend on A16S wiring.
esphome:
  name: "verdify"
  name_add_mac_suffix: true
  platformio_options:
    build_flags: ["-DCORE_DEBUG_LEVEL=1"]

esp32:
  board: esp32dev
  framework:
    type: esp-idf

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  ap: { ssid: "verdify-setup" }
captive_portal:

logger:
  level: INFO

time:
  - platform: sntp
    id: sntp_time
    timezone: "UTC"

# Filesystem for config/plan
littlefs:
  id: fs
  mount: true

i2c:
  sda: 21
  scl: 22
  scan: true

pcf8574:
  - id: pcf0
    address: 0x20
  - id: pcf1
    address: 0x21

switch:
  # Example relay mapped later in config apply (via script)
  - platform: gpio
    id: relay_01
    pin:
      pcf8574: pcf0
      number: 0
      mode: OUTPUT
      inverted: false
  # ... define 16 relays ...

uart:
  id: rs485
  tx_pin: 17
  rx_pin: 16
  baud_rate: 9600
  stop_bits: 1
  parity: NONE

modbus:
  id: mbus
  uart_id: rs485

# HTTP client for API calls
http_request:
  useragent: verdify-controller
  timeout: 10s
  verify_ssl: true

globals:
  - id: device_name
    type: std::string
    restore_value: yes
  - id: claim_code
    type: std::string
    restore_value: yes
  - id: device_token
    type: std::string
    restore_value: yes
  - id: controller_uuid
    type: std::string
    restore_value: yes
  - id: greenhouse_id
    type: std::string
    restore_value: yes
  - id: config_version
    type: int
    restore_value: yes
    initial_value: '0'
  - id: plan_version
    type: int
    restore_value: yes
    initial_value: '0'
  - id: is_climate_controller
    type: bool
    restore_value: yes
    initial_value: 'false'

# Buttons (cool/heat/humid) – actual pins depend on wiring
binary_sensor:
  - platform: gpio
    id: btn_cool
    pin: 32
    filters: [ delayed_on: 50ms ]
    on_press:
      then:
        - script.execute: handle_button_cool
  - platform: gpio
    id: btn_heat
    pin: 33
    filters: [ delayed_on: 50ms ]
    on_press:
      then:
        - script.execute: handle_button_heat
  - platform: gpio
    id: btn_humid
    pin: 34
    filters: [ delayed_on: 50ms ]
    on_press:
      then:
        - script.execute: handle_button_humid

script:
  - id: handle_button_cool
    then:
      - lambda: |-
          Controller::instance().button_override("button_cool");
  - id: handle_button_heat
    then:
      - lambda: |-
          Controller::instance().button_override("button_heat");
  - id: handle_button_humid
    then:
      - lambda: |-
          Controller::instance().button_override("button_humid");

interval:
  - interval: 15s
    then:
      - lambda: |-
          Controller::instance().post_hello_if_needed();
  - interval: 10s
    then:
      - lambda: |-
          Controller::instance().post_sensors_batch();
  - interval: 30s
    then:
      - lambda: |-
          Controller::instance().post_status();
  - interval: 2s
    then:
      - lambda: |-
          Controller::instance().control_loop_tick();
Note: Controller::instance() represents a small C++ custom component that encapsulates config/plan parsing, HTTP calls with Authorization header, staging, job queues, relay supervision, telemetry batching. ESPHome supports Custom Components.
 
13) Custom Component Responsibilities (C++ Outline)
class Controller : public Component {
 public:
  static Controller& instance(); // singleton

  void setup() override;   // read NVS + FS, compute device_name, SNTP
  void loop() override;    // timers for queue + relay supervisor

  // Provisioning
  void post_hello_if_needed();

  // Config/Plan
  void fetch_config_if_stale(); // with If-None-Match
  void fetch_plan_if_stale();

  // Telemetry
  void post_sensors_batch();
  void post_status();
  void post_actuator_edge(const std::string& actuator_id, bool state, const char* reason);
  void post_input_event(const std::string& button_id, const char* action);

  // Control
  void control_loop_tick(); // compute averages, stages, apply rules (if climate controller)
  void button_override(const char* which);

 private:
  // maps populated from config
  struct SensorMap { /* kind, scope, zone_id, modbus addr/reg, scale, offset, poll */ };
  struct ActuatorMap { /* kind, relay_channel, min_on/off, fail_safe, zone_id */ };
  std::unordered_map<UUID, SensorMap> sensors_;
  std::unordered_map<UUID, ActuatorMap> actuators_;
  std::unordered_map<UUID, std::vector<UUID>> fan_groups_;
  RuleGrid rules_;

  // relay supervision
  struct RelayState { bool current; uint64_t last_change_ms; int min_on_ms; int min_off_ms; };
  std::unordered_map<UUID, RelayState> relay_states_;

  // fan rotation
  std::unordered_map<UUID, int> fan_lead_index_;
  std::unordered_map<UUID, int> last_on_count_;

  // overrides
  bool override_active_;
  Stage override_stage_;
  uint64_t override_expires_ms_;

  // queues
  JobQueue irrigation_q_, fert_q_, light_q_;

  // cached telemetry
  std::vector<SensorReading> sensor_buffer_;
};
Agentic checklist
-	MUST wrap all HTTP calls with Authorization header when device_token present.
-	MUST ETag GET config.json / plan.json and write to FS atomically.
-	MUST rate limit telemetry to specified intervals.
 
14) Testing Hooks & Diagnostics
-	Self test endpoint (local web_server, optional): show current stages, averages, enthalpy, next jobs.
-	LED blink codes: boot, claim pending, config applied, plan applied, error.
-	Dry run mode (compile flag): simulate sensor values to test staging and queues without relays.
 
15) Open Questions
> **Open Questions Reference**: All open questions have been consolidated in [GAPS.md](./GAPS.md) for systematic resolution. See sections on Controller Firmware Questions.

**Version:** 2.0 (MVP, HTTP ingest only)
**Role:** Embedded Firmware Engineer (ESPHome/ESP32)
**Scope:** Implementable firmware spec (YAML + custom components) for Kincony A16S‑class ESP32 controllers running ESPHome. Aligns with Project Verdify v2.0 canonical invariants and the “Overall Data Schemas and Contracts Specification”.

---

## 0) Scope, Assumptions & Invariants

**Hardware:** ESP32, 16 relays (Kincony A16S or equivalent), RS‑485 (Modbus), optional I²C expander (PCF8574/MCP23017), 3 physical momentary buttons (cool/heat/humid).
**Identity:** `device_name = "verdify-aabbcc"` (last 3 MAC bytes, lowercase hex). Regex: `^verdify-[0-9a-f]{6}$`.
**Auth:** Device uses a long‑lived `device_token` via X-Device-Token header issued at claim; valid until controller deletion.
**Units & Time:** Metric in all payloads (°C, kPa, hPa, L/min, m³/m³, etc.). All timestamps UTC ISO‑8601 `Z`.
**Climate Loop:** Exactly one climate controller per greenhouse (`is_climate_controller=true`). Only temp/humidity sensors with `include_in_climate_loop=true` are included in climate averages. Exterior sensors are never averaged with interior.
**State Machine:** Grid over `temp_stage ∈ [-3..+3]` × `humi_stage ∈ [-3..+3]`; each cell has MUST\_ON/MUST\_OFF actuator lists and optional `fan_group on_count`. One **fallback** row required.
**Fan Staging:** Fans are grouped; rotation among members; `on_count` = number of fans ON in a group for the row.
**Guard Rails:** Greenhouse immutable rails (min/max temp °C, min/max VPD kPa). Controller clamps any plan/baseline to rails.
**LLM Plan:** Provides min/max temp/vpd targets, stage deltas, hysteresis, irrigation/fertilization/lighting schedules.
**Irrigation Lockout:** Only one valve ON per controller at a time. Overlapping jobs queue FIFO.
**Manual Overrides:** Physical cool/heat/humid buttons can force a `temp_stage/humi_stage` for a configured timeout.
**Fallback:** If no plan row covers “now”, execute baselines + rails from config.
**Transport:** **HTTP only** for MVP (optional gzip). Retries with exponential backoff and jitter.
**Persistence:** NVS/Preferences for `device_token`, controller/greenhouse IDs, ETags, config.json, plan.json.

---

## 1) Sub‑Projects

1. **Hardware Interfaces** (GPIO/I²C/RS‑485 mapping, relays, sensors, buttons)
2. **Boot & Claim** (device\_name, captive portal, POST `/hello`, claim loop)
3. **Config & Plan Handling** (download via ETag, parse, validate, persist)
4. **State Machine Logic** (averaging, VPD/enthalpy, stage determination, rule application)
5. **Schedulers & Queues** (irrigation/fertilization/lighting with lockout)
6. **Manual Overrides** (buttons → temporary stage forcing)
7. **Telemetry & HTTP Client** (payloads, cadence, retries)
8. **Error Handling, Fallback & Logging** (resilience)
9. **YAML Stubs & Custom Components** (implementable ESPHome configs)
10. **Tests & Acceptance** (simulation, assertions)

---

## 2) Hardware Interfaces

### 2.1 Pin/Bus Mapping (example; adjust per board)

| Function                 | Interface            | Notes                         |
| ------------------------ | -------------------- | ----------------------------- |
| RS‑485 A/B               | UART2 (GPIO16/17)    | 9600/19200 bps Modbus RTU     |
| Relays 1..16             | GPIO or I²C expander | PCF8574 or MCP23017 as needed |
| Buttons: cool/heat/humid | GPIO inputs          | Pull‑ups, debounce 30–50 ms   |
| I²C (optional)           | SDA/SCL              | For expanders, displays       |
| Ethernet/Wi‑Fi           | N/A                  | Connectivity for HTTP         |

### 2.2 Supported Sensors (examples)

* Modbus: Temp/RH/Pressure, CO₂, soil moisture, flow meter, kWh.
* Digital/analog: Button inputs, dry contacts.
* Computed: VPD, dew point, enthalpy (in/out).

---

## 3) Boot & Claim

### 3.1 Flow (Mermaid)

```mermaid
flowchart TD
  A[Boot] --> B[Compute device_name = verdify-<mac suffix>]
  B --> C[Start Wi-Fi + Captive Portal + Web UI]
  C --> D[Generate/Load claim_code (NVS or random)]
  D --> E{device_token present?}
  E -- yes --> H[Fetch Config (ETag)] --> I[Fetch Plan (ETag)] --> J[Runtime Loop]
  E -- no --> F[POST /hello {device_name, claim_code, hw_profile, fw}] 
  F --> G{200 token?}
  G -- yes --> G1[Persist device_token, controller_id, greenhouse_id] --> H
  G -- no --> F  %% retry with backoff
```

### 3.2 Device Name & Claim Code

* **device\_name:** Use `esphome.name_add_mac_suffix: true` to produce `verdify-aabbcc`.
* **claim\_code:** 6–8 char random base32 value. Persist to NVS; regenerate only if missing.

### 3.3 `/hello` Request (HTTP, unauthenticated)

```json
{
  "device_name": "verdify-a1b2c3",
  "claim_code": "3PJ6K9",
  "hardware_profile": "kincony_a16s",
  "firmware": "verdify-fw-0.1.0",
  "ts_utc": "2025-08-12T18:00:00Z"
}
```

**Response 200:**

```json
{
  "controller_id": "b9f1c2ba-4d0f-4a5e-b53f-0e5b2f9bdb23",
  "greenhouse_id": "de3a91e5-0f6a-4c5a-9ea4-09a778b9a4a2",
  "device_token": "<opaque-token>",
  "is_climate_controller": true
}
```

**Retry:** Exponential backoff (base 2, max 60 s) + jitter 0–20%.

---

## 4) Config & Plan Handling

### 4.1 Endpoints (authenticated with `X-Device-Token: <device_token>`)

* `GET /controllers/by-name/{device_name}/config` — ETag; 200 or 304
* `GET /controllers/{controller_id}/plan` — ETag; 200 or 304

### 4.2 ETag Strategy

* Store `config_etag` and `plan_etag` in NVS.
* Use `If-None-Match: "<etag>"`. On 304, keep cached. On 200, persist `payload` and `ETag` atomically.

### 4.3 Parsing & Validation (must fail closed)

* Validate JSON against schemas.
* Verify `is_climate_controller` consistency.
* Build maps:

  * `sensor_map`: `sensor_id -> (kind, scope, include_in_loop, modbus params)`
  * `zone_map`: `zone_id -> list[sensor_id]` via `sensor_zone_map` in payload
  * `actuator_map`: `actuator_id -> (kind, relay_channel, min_on_ms, min_off_ms, fail_safe)`
  * `fan_groups`: `fan_group_id -> [actuator_id]`
  * `state_grid`: dict keyed by `(temp_stage, humi_stage)` → {MUST\_ON\[], MUST\_OFF\[], FAN\_COUNTS\[]}
  * `fallback_row` present (enforced).
* Reject config if:

  * Missing fallback row or grid incomplete (49 cells).
  * Multiple `is_climate_controller=true` observed (defensive).
  * A sensor marked `include_in_climate_loop=true` is not reachable (no modbus params or wrong scope).
  * Actuator mapping invalid (duplicate relay\_channel, unknown kind).

### 4.4 Plan Storage

* Store **10 days × 48 slots/day = 480 setpoint rows**.
* Schedules (irrigation/fertilization/lighting) stored as sorted arrays by `ts_utc`.
* NVS/BLOB estimate (typical):

  * setpoints: \~80 bytes × 480 ≈ 38 KB
  * schedules (depends on density): allocate 32–64 KB total.

---

## 5) Runtime Logic

### 5.1 Main Runtime Loop (Mermaid)

```mermaid
stateDiagram-v2
  [*] --> INIT
  INIT --> IDLE : config/plan loaded, queues empty
  IDLE --> MEASURE : sensor tick (10-15s)
  MEASURE --> COMPUTE : averages, VPD, enthalpy
  COMPUTE --> STAGE : baselines+plan deltas+hysteresis, clamp rails
  STAGE --> APPLY_RULES : must_on/off, fan rotate, dwell guard
  APPLY_RULES --> SCHEDULER : run/queue jobs (irrigation/fert/light)
  SCHEDULER --> TELEMETRY : send status/sensors
  TELEMETRY --> IDLE
  STAGE --> OVERRIDE : if button latched
  OVERRIDE --> APPLY_RULES : timeout returns to STAGE
  [*] <-- ERROR : fail-safe (all relays to configured safe)
```

### 5.2 Climate Computations

**Interior averages:** Mean over all temp/humidity sensors where `scope='greenhouse'` and `include_in_climate_loop=true`.
**Exterior:** Separate means over sensors where `scope='external'` (never averaged with interior).
**Pressure:** Use configured site pressure (hPa) if no sensors; else average available.
**VPD (kPa):**

```
es_kPa  = 0.6108 * exp(17.27 * Tin / (Tin + 237.3))
ea_kPa  = es_kPa * (RH_in / 100.0)
VPD     = max(0.0, es_kPa - ea_kPa)
```

**Enthalpy (kJ/kg dry air):**

```
-- T in °C, P in hPa, RH in %
es_hPa = 6.112 * exp(17.67 * T / (T + 243.5))
e_hPa  = RH/100 * es_hPa
w      = 0.62198 * e_hPa / (P - e_hPa)           -- humidity ratio kg/kg
h      = 1.006*T + w*(2501 + 1.86*T)             -- kJ/kg dry air
```

Compute `h_in`, `h_out`, and `enthalpy_delta = h_out - h_in` for dehumidification gate.

### 5.3 Stage Determination (pseudocode)

```pseudo
function compute_stage(now, Tin, RH_in, VPD, config, plan_row):
  // baselines (from config) and plan deltas (from plan_row)
  minT = clamp(plan_row.min_temp_c or config.min_temp_c, gh.min_temp_c, gh.max_temp_c)
  maxT = clamp(plan_row.max_temp_c or config.max_temp_c, gh.min_temp_c, gh.max_temp_c)
  minV = clamp(plan_row.min_vpd_kpa or config.min_vpd_kpa, gh.min_vpd_kpa, gh.max_vpd_kpa)
  maxV = clamp(plan_row.max_vpd_kpa or config.max_vpd_kpa, gh.min_vpd_kpa, gh.max_vpd_kpa)

  // hysteresis (C and %RH or VPD)
  hT = plan_row.hyst_temp_c or config.hyst_temp_c
  hV = plan_row.hyst_vpd_kpa or config.hyst_vpd_kpa

  // temperature stage: negative -> heat, positive -> cool
  if Tin < (minT - 3*hT) then temp_stage = -3
  else if Tin < (minT - 2*hT) then temp_stage = -2
  else if Tin < (minT - 1*hT) then temp_stage = -1
  else if Tin > (maxT + 3*hT) then temp_stage = +3
  else if Tin > (maxT + 2*hT) then temp_stage = +2
  else if Tin > (maxT + 1*hT) then temp_stage = +1
  else temp_stage = 0

  // humidity stage from VPD: low VPD => too humid (dehumidify), high VPD => too dry (humidify)
  if VPD < (minV - 3*hV) then humi_stage = -3      // dehumid strongest
  else if VPD < (minV - 2*hV) then humi_stage = -2
  else if VPD < (minV - 1*hV) then humi_stage = -1
  else if VPD > (maxV + 3*hV) then humi_stage = +3 // humidify strongest
  else if VPD > (maxV + 2*hV) then humi_stage = +2
  else if VPD > (maxV + 1*hV) then humi_stage = +1
  else humi_stage = 0

  // apply planner relative deltas
  temp_stage += (plan_row.temp_stage_delta or 0)
  humi_stage += (plan_row.humi_stage_delta or 0)
  temp_stage = clamp(temp_stage, -3, +3)
  humi_stage = clamp(humi_stage, -3, +3)

  return temp_stage, humi_stage
```

### 5.4 Rule Application (MUST\_ON/OFF, Fan Rotation, Dwell)

```pseudo
function apply_rules(temp_stage, humi_stage, enthalpy_delta, state_grid, fan_groups, now):
  row = state_grid.get((temp_stage, humi_stage), fallback_row)

  // enthalpy gate for dehumidification (stage < 0):
  // if outside air has lower enthalpy (enthalpy_delta < enthalpy_open_kjkg), prefer ventilation (fans/vents) over heating.
  if humi_stage < 0 and enthalpy_delta < gh.enthalpy_open_kjkg:
     // If row specifies heater for dehum, override: disable heater, enable vent/fans as per alt mapping (config option)
     row = row.with_dehumid_strategy('vent_first')  // implementation detail

  // schedule actuator state targets
  targets = {}
  for a in row.must_on_actuators: targets[a] = ON
  for a in row.must_off_actuators: targets[a] = OFF

  // fan group counts
  for fg in row.fan_groups:       // fg = {fan_group_id, on_count}
     members = fan_groups[fg.id]
     lead_idx = next_lead_index[fg.id]
     // rotate lead each time group transitions from 0->>0 active
     order = rotated_order(members, lead_idx)
     for i in range(len(members)):
        targets[members[i]] = (i < fg.on_count) ? ON : (targets.get(members[i]) or OFF)

  // enforce min_on/min_off dwell
  for (actuator, desired) in targets:
     if desired == ON and time_since_off(actuator) < min_off_ms(actuator): desired = HOLD_OFF
     if desired == OFF and time_since_on(actuator) < min_on_ms(actuator): desired = HOLD_ON

  // write relays only when actual != desired and dwell allows
  for actuator in sorted_by_dependencies(targets):
     set_relay(actuator, resolved_state(desired))

  return
```

### 5.5 Schedulers & Queues (Irrigation/Fert/Lighting)

* Maintain **one irrigation valve ON at a time** per controller.
* Two queues:

  * `ready_queue`: jobs whose `ts_utc <= now` and not running
  * `running_job`: current valve job (with deadline `start + duration_s`)
* Overlaps → enqueue FIFO. After completion, start next job if available.
* Lighting & fertilization do **not** lock irrigation (unless same actuator). If same actuator kind/channel, serialize.

```pseudo
function scheduler_tick(now):
  // load plan jobs up to lookahead (e.g., +2h) into ready_queue
  for job in plan_jobs_between(last_tick, now):
    enqueue(ready_queue, job)

  // if running_job active, check completion
  if running_job and now >= running_job.end_time:
    stop_valve(running_job.actuator_id)
    running_job = null

  // if no running_job, pull next eligible from queue
  while not running_job and not empty(ready_queue):
    j = dequeue(ready_queue)
    if actuator_available(j.actuator_id):
      start_valve(j.actuator_id); running_job = j
    else:
      // conflict: requeue with slight delay to avoid busy-wait
      defer(ready_queue, j, +30s)
```

### 5.6 Manual Overrides

```pseudo
on_button_press(kind):
  cfg = button_config[kind]  // {target_temp_stage, target_humi_stage, timeout_s}
  override.active = true
  override.until = now + cfg.timeout_s
  override.temp_stage = cfg.target_temp_stage
  override.humi_stage = cfg.target_humi_stage

if override.active and now > override.until:
  override.active = false
```

During override, `compute_stage()` returns `(override.temp_stage, override.humi_stage)`.

### 5.7 Fallback Behavior

* If **no valid plan row** for `now`: use config baselines (min/max temp/vpd, hyst, deltas=0).
* If **plan expired**: continue last known plan for 24h (configurable), then switch to baselines.
* On **sensor read failures**: 
  - Exclude failed sensors from averages calculation
  - If all critical sensors offline: hold last stage for 5 minutes, then activate fallback state
  - Report offline sensors in status telemetry via `offline_sensors: [sensor_ids]`
  - Sensor considered offline if no reading received for >60 seconds (configurable timeout)

---

## 6) Telemetry & HTTP

### 6.1 Cadence

* **Sensors batch:** every 10–15 s
* **Status frame:** every 30 s
* **Actuator edge:** immediately upon change (ON/OFF)
* **Input event:** on press/release

### 6.2 Endpoints (X-Device-Token auth)

* `POST /api/v1/telemetry/sensors`
* `POST /api/v1/telemetry/actuators`
* `POST /api/v1/telemetry/status`
* `POST /api/v1/telemetry/inputs`
* Optional: `POST /api/v1/telemetry/batch` (envelope contains arrays for the above)

### 6.3 Payloads (align with master spec)

**Sensors**

```json
{
  "controller_id": "b9f1c2ba-...-bdb23",
  "device_name": "verdify-a1b2c3",
  "frames": [
    {
      "ts_utc": "2025-08-12T18:00:02Z",
      "readings": [
        {"sensor_id":"...", "kind":"temperature", "value":22.7},
        {"sensor_id":"...", "kind":"humidity", "value":54.1},
        {"sensor_id":"...", "kind":"air_pressure", "value":842.3}
      ]
    }
  ]
}
```

**Actuator Edges**

```json
{
  "controller_id": "b9f1c2ba-...-bdb23",
  "events": [
    {
      "ts_utc": "2025-08-12T18:00:05Z",
      "actuator_id": "....",
      "state": true,
      "reason": "STATE_MACHINE:temp=+2,humi=-1"
    }
  ]
}
```

**Status**

```json
{
  "controller_id": "b9f1c2ba-...-bdb23",
  "frame": {
    "ts_utc": "2025-08-12T18:00:30Z",
    "temp_stage": 1,
    "humi_stage": -1,
    "avg_interior_temp_c": 23.1,
    "avg_interior_rh_pct": 58.2,
    "avg_interior_pressure_hpa": 841.9,
    "avg_exterior_temp_c": 19.0,
    "avg_exterior_rh_pct": 71.0,
    "avg_exterior_pressure_hpa": 840.8,
    "avg_vpd_kpa": 0.85,
    "enthalpy_in_kj_per_kg": 55.4,
    "enthalpy_out_kj_per_kg": 50.1,
    "override_active": true,
    "plan_version": 12,
    "plan_stale": false,
    "offline_sensors": ["sensor-uuid-1", "sensor-uuid-2"],
    "fallback_active": false
  }
}
```

**Input Events**

```json
{
  "controller_id": "b9f1c2ba-...-bdb23",
  "events": [
    {"ts_utc":"2025-08-12T18:00:00Z","button_kind":"cool","latched":true}
  ]
}
```

### 6.4 HTTP Client & Retries

* Headers: `X-Device-Token: <device_token>`, `Content-Type: application/json`, optional `Content-Encoding: gzip`.
* Retries: exponential backoff (1, 2, 4, 8… max 60 s) + jitter. Drop oldest sensor frames first if queue > 100 frames.

---

## 7) Error Handling & Logging

* **Configuration errors:** refuse to arm outputs; periodically retry downloads; send heartbeat status with error codes.
* **Sensor faults:** mark sensor offline after `N` consecutive failures; exclude from averages; report in status.
* **Relay faults:** if actuator toggling fails (detected via optional feedback), mark as degraded; stop cycling.
* **Network:** queue telemetry until cap; on cap, drop sensor frames (never drop edges).
* **Fail‑safe:** On unrecoverable error, set all actuators to `fail_safe_state` and keep pulsing telemetry attempts.

---

## 8) YAML Stubs (ESPHome)

> Adjust pins/channels per board. Add custom components where required.

```yaml
esphome:
  name: verdify
  name_add_mac_suffix: true
  project:
    name: verdify.controller
    version: 0.1.0

esp32:
  board: esp32dev

logger:
  level: INFO

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_pass
  ap:  # captive portal fallback
    ssid: "Verdify-Setup"

captive_portal:

web_server:
  port: 80

time:
  - platform: sntp
    id: sntp_time
    timezone: UTC

uart:
  id: uart_modbus
  tx_pin: GPIO17
  rx_pin: GPIO16
  baud_rate: 19200
  stop_bits: 1
  parity: NONE

modbus:
  id: modbus1
  uart_id: uart_modbus

i2c:
  sda: GPIO21
  scl: GPIO22
  scan: true

# Example: PCF8574 for relays (update addresses and mapping)
pcf8574:
  - id: pcf1
    i2c_id: i2c_bus
    address: 0x20

switch:
  - platform: gpio
    name: "Relay 1"
    id: relay_1
    pin:
      pcf8574: pcf1
      number: 0
      mode: OUTPUT
      inverted: false
  # ... repeat mapping for 16 relays

binary_sensor:
  - platform: gpio
    id: btn_cool
    name: "Button Cool"
    pin:
      number: GPIO32
      mode: INPUT_PULLUP
      inverted: true
    filters:
      - delayed_on: 30ms
    on_press:
      - lambda: |-
          id(ctrl).on_button_press("cool");
  - platform: gpio
    id: btn_heat
    name: "Button Heat"
    pin:
      number: GPIO33
      mode: INPUT_PULLUP
      inverted: true
    filters:
      - delayed_on: 30ms
    on_press:
      - lambda: |-
          id(ctrl).on_button_press("heat");
  - platform: gpio
    id: btn_humid
    name: "Button Humid"
    pin:
      number: GPIO34
      mode: INPUT_PULLUP
      inverted: true
    filters:
      - delayed_on: 30ms
    on_press:
      - lambda: |-
          id(ctrl).on_button_press("humid");

# HTTP client for API calls
http_request:
  id: http_client
  useragent: verdify-controller/0.1
  timeout: 10s

text_sensor:
  - platform: template
    id: device_name
    name: "Device Name"
    lambda: |-
      // 'esphome' exposes hostname; ensure it's 'verdify-<suffix>'
      return App.get_name().c_str();

# Custom component for core logic (C++)
custom_component:
  - id: ctrl
    lambda: |-
      auto c = new VerdifyController();
      return {c};
```

> Implement `VerdifyController` to encapsulate boot, claim, config/plan fetch, state machine, telemetry, and queues. Use ESPHome’s `App.register_component(c)` or the `custom_component` wrapper above.

---

## 9) Pseudocode — Key Routines

### 9.1 Boot/Claim/Fetch

```pseudo
setup():
  device_name = get_hostname()          // "verdify-aabbcc"
  claim_code = nvs_get("claim_code") or gen_random_code()
  device_token = nvs_get("device_token")
  if not device_token:
    do
      resp = http_post("/hello", {...})
      if resp.status == 200:
        nvs_put(token, controller_id, greenhouse_id)
      else sleep(backoff())
    while not token
  fetch_config_if_stale()
  fetch_plan_if_stale()
```

### 9.2 Sensor Read Tick (10–15 s)

```pseudo
read_sensors():
  for s in sensors:
    val = modbus_read(s)
    if valid: cache[s.id] = val
    else mark_offline(s)

compute_averages():
  interior_T = mean(values where scope='greenhouse' and kind='temperature' and include_in_loop)
  interior_RH = mean(values where scope='greenhouse' and kind='humidity' and include_in_loop)
  exterior_T = mean(values where scope='external' and kind='temperature')
  exterior_RH = mean(values where scope='external' and kind='humidity')
  P = interior_pressure if available else gh.site_pressure_hpa
  VPD = compute_vpd(interior_T, interior_RH)
  h_in = enthalpy(interior_T, interior_RH, P)
  h_out = enthalpy(exterior_T, exterior_RH, P)
```

### 9.3 Stage + Apply + Telemetry

```pseudo
loop():
  if now - last_sensor_read >= 10s: read_sensors(); compute_averages()
  if override.active and now > override.until: override.active = false

  plan_row = plan.row_for(now) or null
  if override.active:
     (ts, hs) = (override.temp_stage, override.humi_stage)
  else:
     (ts, hs) = compute_stage(now, interior_T, interior_RH, VPD, config, plan_row)

  apply_rules(ts, hs, h_out - h_in, state_grid, fan_groups, now)
  scheduler_tick(now)

  if now - last_status >= 30s: post_status()
  if now - last_sensor_post >= 10s: post_sensors_batch()
```

---

## 10) Validation & Acceptance {#validation-acceptance}

> **Validation Reference**: For complete validation rules and business invariants, see [Business Invariants in OVERVIEW.md](./OVERVIEW.md#business-invariants).

**Validation Rules (firmware enforces):**

* **Configuration integrity**: Device name matches runtime hostname; state grid complete with fallback
* **Climate loop**: Only `include_in_climate_loop=true` sensors contribute to interior averages; exterior sensors excluded  
* **Safety lockouts**: Irrigation valve lockout (never two valves ON concurrently per controller)
* **Override management**: Manual overrides expire at configured timeout; telemetry reflects active state
* **Data formats**: All timestamps UTC; all values metric units; device name regex validation

**Acceptance Tests (simulate where needed):**

1. **Stage transitions:** Synthetic Tin/RH sequences trigger temp/humi stages across −3..+3 with hysteresis (no chatter).
2. **Fan rotation:** Over 10 activations, each member of a fan\_group becomes lead at least once.
3. **Dwell timers:** Commands within dwell windows are held (no relay chatter).
4. **Irrigation lockout:** Overlapping jobs execute sequentially; exact durations respected (±1 s).
5. **Override:** Press “cool” forces configured stage for timeout, then reverts; telemetry frames reflect override.
6. **Fallback:** With plan missing/expired, controller uses baselines + rails; continues stable operation for ≥24 h.
7. **HTTP resilience:** With injected 5xx/timeout errors, retries/backoff occur; edges are never dropped; sensor frames drop only when queue cap exceeded.

---

## 11) Risks & Edge Cases

* **Clock skew before SNTP:** Delay actuation until time is valid; allow limited local control with conservative defaults.
* **Sensor drift:** Consider simple plausibility checks (e.g., ΔT > 10°C in 10 s → discard).
* **Network flaps:** Queue growth; ensure cap and eviction policy prioritize edges/status.
* **Memory pressure:** Ensure plan/schedule storage fits NVS; consider chunked plan retrieval if needed.

---

## 12) Implementation Guidance for Agentic Coder

1. **Core Class (C++):** Implement `VerdifyController` with methods: `boot_claim()`, `fetch_config_if_stale()`, `fetch_plan_if_stale()`, `read_sensors()`, `compute_averages()`, `compute_stage()`, `apply_rules()`, `scheduler_tick()`, `post_*()`, `on_button_press(kind)`.
2. **HTTP Client:** Wrap ESPHome `http_request` to support X-Device-Token auth, JSON POST, GET with `If-None-Match`, parsing, and backoff strategy.
3. **NVS Storage:** Keys: `device_token`, `controller_id`, `greenhouse_id`, `claim_code`, `config_etag`, `plan_etag`, `config_blob`, `plan_blob`, `fan_lead_idx/<fan_group_id>`.
4. **Relays Driver:** Abstract `set_relay(actuator_id, state)` with dwell enforcement and edge telemetry emission.
5. **Sensors Driver:** Map Modbus registers per config; include scaling/offset; mark offline after N consecutive errors.
6. **Math Utils:** Implement `vpd(T, RH)` and `enthalpy(T, RH, P)` with numerically stable exponentials.
7. **Schedulers:** Priority queues per type; hard lock for irrigation valves.
8. **Overrides:** Debounced button ISR → queue event → override latch with timeout.
9. **Telemetry Serializer:** Build JSON exactly as in §6.3; timestamps from SNTP; include `device_name` and `controller_id`.
10. **Diagnostics:** Web UI page showing device\_name, claim\_code, token status, config/plan versions, next jobs.

**Dependencies:** 1→2→3 foundational; 4–7 can proceed in parallel after 3; 8–9 after core loop; 10 last.

---

## End‑of‑Output Checklist

* [x] Boot & claim flow defined with payloads, retries, and persistence.
* [x] Full config & plan handling with ETag, validation, and storage.
* [x] State machine logic: averages, VPD, enthalpy, stage determination, clamping.
* [x] Rule application: MUST\_ON/OFF, fan rotation, dwell, enthalpy gate.
* [x] Schedulers with irrigation lockout and FIFO queue.
* [x] Manual overrides with timeout and telemetry flag.
* [x] Telemetry payload schemas, cadence, HTTP/retries.
* [x] YAML stubs compatible with ESPHome; custom component hook provided.
* [x] Tests & acceptance criteria listed; all invariants restated.
