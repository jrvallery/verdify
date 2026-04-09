---
title: Equipment
tags: [equipment, hardware, reference]
date: 2026-03-28
type: reference
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Equipment Inventory
198 ESP32 entities across 33 relays, 16 sensor streams, 49 grow light fixtures, and 45 mister nozzles.

<div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; margin: 1.5rem 0;">

![North wall utility area: Lennox heater, circulation fan, solenoid manifold, stainless work sink, and controller](/static/photos/north-wall-utility-wide.jpg)

![Kincony KC868-E16P relay board with 16-channel relays, DIN-rail breaker, transformer, and color-coded wiring](/static/photos/kincony-relay-closeup.jpg)

![Tzone RS485 climate sensor probe in louvered housing](/static/photos/tzone-sensor-north.jpg)

</div>

## Climate Control

| Equipment | Model | Power | Cost/hr | Control |
|-----------|-------|-------|---------|---------|
| Electric heater | Generic (discontinued) | 1,500W | $0.167 | ESP32 → SSR |
| Gas furnace | Lennox LF24-75A-5 | 75,000 BTU | $0.623 | ESP32 → SSR |
| Exhaust fan ×2 | KEN BROWN 18" Shutter | 52W each | $0.006 | ESP32 → SSR |
| Intake vent | Unknown actuator | ~10W | $0.001 | ESP32 → SSR |
| Fog machine | AquaFog XE 2000 HumidiFan | 1,644W | $0.182 | ESP32 → SSR |

## Misting

| Zone | Active Heads | Active Nozzles | Mount |
|------|-------------|----------------|-------|
| South | 6 | 30 | Wall-mounted, 2 rows |
| West | 3 | 15 | Overhead |
| Center | 5 | 25 | Overhead |
Nozzles: Micro Drip 360° emitters, 1/2", 1–5 Bar, 0–300 L/H adjustable.

## Lighting

| Circuit | Fixtures | Model | Watts | CRI |
|---------|----------|-------|-------|-----|
| Grow (2FT) | 34 | Barrina T8 24W | 816W | 80 |
| Main (4FT) | 15 | Barrina T8 42W | 630W | 98 |
→ See [[climate/lighting|Grow Lighting]] for details.

## Sensors

| Sensor | Model | Count | Accuracy | Protocol |
|--------|-------|-------|----------|----------|
| Climate probes | Tzone RS485 (SHT3X) | 6 | ±0.3°C, ±2% RH | Modbus RTU |
| Soil probes | DFRobot SEN0600/SEN0601 | 3 | Moisture, temp, EC | Modbus RTU |
| CO₂ | Kincony analog | 1 | 0–10K ppm | ADC (GPIO36) |
| Light (indoor) | Kincony LDR | 1 | Poor (saturates 28K lux) | ADC (GPIO35) |
| Water flow | DAE AS200U-75P | 1 | Pulse counter | GPIO33 |
| Hydro quality | YINMIK | 1 | pH, EC, TDS, ORP, temp | BLE via HA |
| Weather station | Tempest | 1 | 20 outdoor metrics | API via HA |
| Energy | Shelly EM50 | 1 | 3 circuits | HTTP API |
| Cameras | Amcrest IP8M-T2599EW-AI-V3 | 2 | 4K turret, PoE, 125° FOV | Frigate |

## Controller

![ESP32-based controller enclosure with relay modules and transformer](/static/photos/esp32-controller.jpg)

| Property | Value |
|----------|-------|
| Board | Kincony KC868-E16P |
| Firmware | ESPHome 2026.3.0 |
| I/O Expanders | 2× PCF8574 (output), 1× PCF8574 (input, unused) |
| Relays | CG SSR-25DA (DC→AC, 25A) |
| Entities | 198 total |
| Address | 192.168.10.111 |

## Water

![Rinnai tankless water heater mounted on the north wall with digital temperature display](/static/photos/rinnai-water-heater.jpg)

| Equipment | Model | Specs |
|-----------|-------|-------|
| Water heater | Rinnai RE140iN | 140K BTU tankless NG, 5.3 GPM |
| Water meter | DAE AS200U-75P | 3/4" NPT, pulse output, gallons |
---

## Relay Map
PCF8574 I/O expander pin assignments. All relays are CG SSR-25DA (DC→AC, 25A).

### Output Expander 1 (pcf_out_1, 0x20)

| Pin | Equipment | Type |
|-----|-----------|------|
| 0 | West misters (clean) | Water valve |
| 1 | West misters (fert) | Water valve |
| 2 | South misters (fert) | Water valve |
| 3 | South misters (clean) | Water valve |
| 4 | Wall drip (clean) | Water valve |
| 5 | *unused* | — |
| 6 | Center drip (fert) | Water valve (DISCONNECTED) |
| 7 | Center drip (clean) | Water valve (DISCONNECTED) |

### Output Expander 2 (pcf_out_2, 0x21)

| Pin | Equipment | Type |
|-----|-----------|------|
| 0 | Wall drip (fert) | Water valve |
| 1 | Fert master valve | Gates ALL fert delivery |
| 2 | Gas furnace (Heat2) | Lennox LF24-75A-5 |
| 3 | Exhaust fan 1 | KEN BROWN 18" |
| 4 | Exhaust fan 2 | KEN BROWN 18" |
| 5 | Intake vent | Mechanical actuator |
| 6 | Fog machine | AquaFog XE 2000 |
| 7 | Electric heater (Heat1) | Space heater |

### Input Expander (pcf_in, 0x24)
Nothing connected. Part of the Kincony E16P board, unused.

<div class="grafana-controls"></div>

<div class="pg s4"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-equipment/?orgId=1&panelId=2&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-equipment/?orgId=1&panelId=3&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-equipment/?orgId=1&panelId=4&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-equipment/?orgId=1&panelId=5&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-equipment/?orgId=1&panelId=6&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-equipment/?orgId=1&panelId=7&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-equipment/?orgId=1&panelId=8&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>

<div class="pg s2"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-equipment/?orgId=1&panelId=10&theme=dark" width="100%" height="250px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-equipment/?orgId=1&panelId=11&theme=dark" width="100%" height="250px" frameborder="0"></iframe></div>

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-equipment/?orgId=1&panelId=17&theme=dark" width="100%" height="320px" frameborder="0"></iframe></div>
