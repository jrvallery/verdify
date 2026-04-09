---
title: "North Zone"
tags: [zones, north, equipment]
date: 2026-03-28
type: zone
zone: north
sensor: "Modbus addr 2 (temp, RH, VPD)"
orientation: "Back wall, shared with house"
water_systems: []
position_scheme: "No planting positions"
wall_length: "13 ft"
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# North Zone

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=11&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>

<div class="grafana-controls"></div>
Equipment only. No planting. The 13-foot north wall is shared with the house's bar and sunroom. This is the control room — where the ESP32 controller, intake vent, and house door live.

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1.5rem 0;">

![North wall — irrigation manifold, stainless sink, Lennox heater overhead](/static/photos/north-wall-equipment.jpg)

![Irrigation valve manifold closeup with copper piping and solenoid assemblies](/static/photos/north-wall-manifold.jpg)

![North wall overview — equipment zone with the house door, vent intake, and mechanical systems](/static/photos/north-wall-overview.jpg)

</div>

## Climate Profile

| Metric | Value | Context |
|--------|-------|---------|
| Temperature | Buffered by house. Warm afternoon (93°F+ peak PM). | House thermal mass stores heat, releases in afternoon |
| Overnight | ~68°F floor without heaters | House heat leaks through shared wall |
| Humidity | Variable | Intake vent introduces outdoor air here |
| Light | Lowest natural light (north-facing) | Behind the peaked roof ridge |

### The 2 PM Anomaly
On March 25, the north zone hit 93.6°F at 2 PM — hotter than the south zone's 85.2°F at that hour. The south zone had already peaked and was cooling via exhaust fans. The north zone, buffered by the house's thermal mass and far from the fans, retained its heat longer. This means average temperature *overstates* the stress in growing zones and *understates* it in the equipment zone.

## Physical Layout

| Feature | Details |
|---------|---------|
| House door | Interior door to bar/sunroom. Always closed. Passive thermal bridge. |
| Intake vent | 24"×24" (4 sq ft opening). Mechanical actuator with screen. pcf_out_2 pin 5. |
| ESP32 controller | Kincony KC868-E16P board. 192.168.10.111. |
| Relay panels | PCF8574 I/O expanders → SSR-25DA solid-state relays |
| Camera | Amcrest IP8M-T2599EW-AI-V3, 4K turret, PoE |

### Airflow Role
The north wall is the **air intake** side of the greenhouse's airflow path:
```
North (intake vent + house door) 
  → Center (fog machine) 
    → South (exhaust fans)
```
When the economiser gate determines outdoor enthalpy is lower than indoor (cooler and/or drier outside), the vent opens to pull in free cooling. When the vent is closed, the house door still allows passive heat exchange through the shared wall.

## Sensor Coverage

| Sensor | Address | Interval | Accuracy |
|--------|---------|----------|----------|
| Temperature | Modbus addr 2 (Tzone SHT3X) | 10s | ±0.3°C |
| Relative Humidity | Same probe | 10s | ±2% RH |
| VPD | Derived on ESP32 | 10s | Calculated |
| CO₂ | Kincony wired analog, 0-5V, 0-10K ppm | 10s | GPIO-based |
| Light (lux) | Kincony LDR, GPIO35 | 10s | ⚠️ Saturates at ~28K lux |
**Note:** The CO₂ sensor and lux sensor are positioned in/near the north zone, reading greenhouse-average rather than zone-specific values.

## Thermal Buffer Value
The house connection is the greenhouse's most valuable passive climate control feature:

| Scenario | Effect |
|----------|--------|
| Cold winter night (20°F outdoor) | House leaks heat → greenhouse stays ~68°F floor without heaters on moderate nights |
| Moderate spring night (45°F) | No heaters needed at all — house heat maintains setpoint |
| Hot summer day (95°F) | Minimal effect — house AC doesn't reach greenhouse meaningfully |
The north wall acts as a thermal flywheel, damping temperature swings. Combined with the concrete slab's heat storage, this gives the greenhouse surprisingly good overnight thermal retention.

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=11&theme=dark" width="100%" height="320px" frameborder="0"></iframe></div>
→ See [[climate/heating|Heating Systems]] for the staged heating strategy.
→ See [[climate/cooling|Cooling & Ventilation]] for the intake vent and economiser.
→ See [[greenhouse/zones/|All Zones]]
