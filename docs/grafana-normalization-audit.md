# Grafana Normalization Audit

Audited: 2026-04-30  
Normalized/deployed: 2026-04-30
Scope: live Grafana dashboards, repo/worktree dashboard JSON, website embeds, firmware sensor YAML, `sensor_registry`, and DB schema/catalog surfaces.

## Executive Summary

Live Grafana currently exposes 56 dashboards and 912 panels. The public website embeds 209 Grafana iframes across 29 pages after removing misleading duplicates and raising low-height complex embeds. `make site-doctor` currently reports 0 stale dashboard or panel IDs.

The dashboard estate has been mechanically normalized and redeployed. The final full render audit completed with 912/912 panels rendered OK, 0 style findings, and 0 accuracy findings. The website validation gate also passed with 78 pages, 209 Grafana iframes, 19 referenced dashboard UIDs, 57 local image refs, 424 internal links, and 0 findings.

High-priority findings fixed in the normalization pass:

- VPD is returned in kPa, but dashboards use `pressurekpa`, `kPa`, and sometimes `pressurePascal`.
- Stress panels still often use Grafana unit `h`; Grafana renders large hour values as days, which misleads daily stress-hour charts.
- Several panels titled “Stress Hours” are actually plotting setpoint values from `setpoint_changes`.
- Some planning score panels query `plan_journal.score`, but the live schema uses `outcome_score`.
- Some forecast/planning panels contain invalid SQL such as `c.avg(temp_avg)`.
- Cost/monthly panels in older dashboards query non-existent `daily_summary.ts` and `cost_total_usd`.
- DLI panels mix `none`, `short`, and `mol/m²/d`, with inconsistent thresholds.
- ESP32 heap panels mix `kbytes`, `deckbytes`, and byte-scaled thresholds.
- Entity colors drift across dashboards for zones, equipment, outdoor context, DLI, and planner compliance/stress.
- The repo/worktree dashboard snapshot had drifted from live: `site-evidence-planning-quality` was missing locally while obsolete `site-evidence-compliance` remained provisioned.
- Website embeds reused the wrong panels, duplicated the same proof charts, and squeezed complex graphs into 130px image slots.
- Parallel full-panel rendering needed pacing, checkpoint, progress, and resume support to be reliable against Grafana renderer rate limits.

Render artifact: `docs/grafana-embedded-render-audit-2026-04-30.md`.

Final full-audit command:

```bash
scripts/audit-grafana.py --render all \
  --resume-json /tmp/verdify-grafana-audit-all-normalized-rendered-final2.json \
  --json-report /tmp/verdify-grafana-audit-all-normalized-rendered-final3.json \
  --markdown-report docs/grafana-panel-catalog.md
```

Final result: 56 dashboards, 912 panels, `render=ok` for all 912 panels, 0 style findings, 0 accuracy findings.

## Canonical Units

Use these as the dashboard contract unless a panel explicitly documents a different transformed metric.

| Metric family | Source examples | Canonical Grafana unit | Label convention |
|---|---|---:|---|
| Air temperature | `climate.temp_*`, `weather_forecast.temp_f` | `fahrenheit` | `Indoor Temp`, `Outdoor Temp`, `North Temp` |
| VPD | `climate.vpd_*`, `weather_forecast.vpd_kpa` | `pressurekpa` | `Indoor VPD`, `Outdoor VPD`, `VPD High`, `VPD Low` |
| Relative humidity | `climate.rh_*`, `outdoor_rh_pct` | `percent` | `Indoor RH`, `Outdoor RH`, `North RH` |
| Compliance | `*_compliance_pct` | `percent` | `Temp Compliance %`, `VPD Compliance %`, `Total Compliance %` |
| Stress duration | `*_stress_h`, runtime hours | `short` with axis label `Hours` | `Temp Stress Hours`, `VPD Stress Hours` |
| Runtime minutes | `runtime_*_min` | `min` | `Heat 1 Runtime`, `Fan 1 Runtime` |
| Runtime hours | `runtime_*_h`, minute fields divided by 60 | `short` with axis label `Hours` | `Heat 1 Hours`, `Mister South Hours` |
| Daily light integral | `dli_today`, derived DLI views | `mol/m²/d` | `Sensor DLI`, `Estimated Plant DLI`, `Target DLI` |
| Illuminance | `lux`, `outdoor_lux` | `lux` | `Indoor Illuminance`, `Outdoor Illuminance` |
| Irradiance | `solar_irradiance_w_m2`, `solar_w_m2` | `watt/m²` | `Solar Irradiance` |
| Power | Shelly power, `power_w` | `watt` | `Power`, `Greenhouse Power` |
| Energy | `kwh_*` | `kwatth` | `Electric Energy` |
| Cost | `cost_*` | `currencyUSD` | `Electric Cost`, `Gas Cost`, `Water Cost`, `Total Cost` |
| Water volume | `water_*_gal`, `mister_water_today` | `gal` | `Water Used`, `Mister Water` |
| Water flow | `flow_gpm` | `gal/min` | `Water Flow` |
| Soil moisture | `soil_moisture_*`, `moisture_*` | `percent` or `% VWC` in label | `South 1 Soil Moisture` |
| Soil/hydro EC | `soil_ec_*`, `hydro_ec_us_cm` | `µS/cm` | `Soil EC`, `Hydro EC` |
| pH | `hydro_ph`, `ph_*` | `pH` or `none` with label `pH` | `Hydro pH`, `Runoff pH` |
| CO2 | `co2_ppm` | `ppm` | `CO2` |
| Wind speed | `wind_*_mph` | `velocitymph` | `Wind Speed`, `Wind Gust`, `Wind Lull` |
| Wind direction | `wind_direction_*_deg` | `degree` | `Wind Direction` |
| Pressure | `pressure_hpa` | `pressurehpa` | `Barometric Pressure` |
| Heap | `heap_kb` | `kbytes` | `Free Heap` |
| Uptime/age seconds | `uptime_s`, `age_s` | `s` | `Uptime`, `Data Age` |

## Canonical Colors

Use the same hue for an entity everywhere. Overlay panels may reduce alpha, but should not change hue.

| Entity / family | Color |
|---|---:|
| Indoor actual / controlled variable | `#73BF69` |
| Outdoor / ambient context | `#8C8C8C` |
| Forecast | `#42A5F5` |
| Target / reference / planned value | `#FFCA28` |
| High ceiling / hot / too high | `#EF5350` |
| Low floor / cold / too low | `#42A5F5` |
| Total / aggregate | `#73BF69` or neutral `#B0BEC5` when not a “good” value |
| South zone | `#EF5350` |
| North zone | `#42A5F5` |
| East zone | `#AB47BC` |
| West zone | `#66BB6A` |
| Center zone | `#E040FB` |
| Heat 1 | `#FF9800` |
| Heat 2 | `#F4511E` |
| Fan 1 | `#26A69A` |
| Fan 2 | `#5C6BC0` |
| Vent | `#FFCA28` |
| Fog | `#00ACC1` |
| Mister South | `#CE93D8` |
| Mister West | `#F48FB1` |
| Mister Center | `#E040FB` |
| Drip Wall | `#4DB6AC` |
| Drip Center | `#4FC3F7` |
| Grow Light Main | `#9CCC65` |
| Grow Light Grow | `#C6FF00` |
| Electric cost | `#FF9800` |
| Gas cost | `#F44336` |
| Water cost | `#2196F3` |
| Sensor DLI | `#FFA726` |
| Estimated Plant DLI | `#73BF69` |
| Target DLI | `#8C8C8C` |
| Solar irradiance | `#FFA726` |
| Outdoor illuminance | `#FDD835` |

## Confirmed Deviations And Fixes

### Unit and Label Deviations

- Fixed VPD target-band panel units to `pressurekpa` where SQL returns kPa.
- Fixed DLI panels to use `mol/m²/d` where the panel plots daily light integral.
- Fixed solar irradiance panels to use `watt/m²`.
- Fixed free-heap panels to use `kbytes`.
- Fixed raw `°F` temperature units to Grafana `fahrenheit`.
- Fixed water flow from `gpm` to `gal/min`.
- Fixed daily stress/runtime hour storytelling to use `short` plus axis label `Hours`, avoiding Grafana's misleading day conversion for unit `h`.

### SQL and Derived-Metric Deviations

- Fixed older stress-hour panels that queried `setpoint_changes` values instead of duration by moving them to `daily_summary.stress_hours_*` where available.
- Fixed planning score panels from `avg(score::numeric)` to the live `outcome_score` column where that old query remained.
- Fixed invalid SQL such as `c.avg(temp_avg)` and `c.avg(vpd_avg)`.
- Fixed economics panels that queried non-existent `daily_summary.ts` and `cost_total_usd`.
- Fixed water-as-climate-control panels that queried non-existent `diagnostics.cumulative_gallons_today`.
- Fixed mister effectiveness filters from `zone='south'` style predicates to the live `equipment='mister_south'` convention.
- Fixed average daily cost panels that excluded zero-cost days and inflated averages.
- Daily-summary panels still commonly filter `date::timestamptz`. Prefer `date BETWEEN $__timeFrom()::date AND $__timeTo()::date`, or plot date buckets at local noon with `(date + time '12:00')::timestamptz`.
- Forecast-vs-planned-vs-actual panels mix outdoor forecast, indoor actual, and planned control bounds. That can be a valid story, but only if the title and legend explicitly describe the domains.
- Planner “total stress hours” currently means summed stress-category hours. Because temperature and VPD can be stressed simultaneously, it can exceed 24 hours/day. The homepage and planning-quality graph now label this `Total Stress-Category Hours` and render it as a line over stacked temperature/VPD bars.

### Sensor and Data Catalog Drift

- `verdify_schemas/catalog.py` is a crop catalog, not a sensor catalog. The actual sensor catalog is split across firmware YAML, `sensor_registry`, `ingestor/entity_map.py`, migrations, topology import constants, and Grafana JSON.
- Soil probe naming is mostly correct in dashboards (`South 1`, `South 2`, `West`), but older schema/topology references still mention stale `soil.south`/`soil.center` and `moisture_south`/`moisture_center`.
- Tempest precipitation rate is exposed by firmware as `in/hr`, but ingest mapping historically conflates rate and accumulation. Reserve `precip_intensity_in_h` for rate and `precip_in` for amount.
- Hydro TDS should be `hydro_tds_ppm`; old `hydro_tds_ppt` references still appear in older migrations/staleness logic.
- `outdoor_lux` should be the canonical Tempest outdoor illuminance field. `outdoor_illuminance` should be documented as an alias or retired.
- DLI correction and target semantics are not centralized. Dashboards contain hardcoded targets and correction factors, so different panels can tell different DLI stories.

### Color and Style Deviations

- Normalized zone, equipment, indoor/outdoor, DLI, cost, compliance, and stress colors using the canonical color map above.
- Removed production `REVIEW —` title prefixes.
- Normalized default time-series `lineWidth` and `spanNulls` defaults across dashboards.

### Website Embed Deviations

- Fixed `/evidence/operations` duplicate/mismatched panel use and raised full charts to readable heights.
- Reduced duplicate proof panels on `/evidence/dashboards`.
- Removed the duplicate opening mini-grid from `/greenhouse/zones/index`.
- Replaced duplicate low-height south-zone embeds with one temperature chart and one soil-moisture chart.
- Moved equipment runtime embeds under a live runtime section and removed the duplicate full-width runtime panel.
- Raised crop DLI embeds from 130px to 320px.
- Removed unrelated zone climate panels from `/greenhouse/structure`.
- Raised low-height complex `/climate` embeds to 320-340px.

## Immediate Fix Applied

The web worktree dashboard snapshot was brought back into line with live site evidence dashboards:

- Added `grafana/dashboards/site-evidence-planning-quality.json`.
- Added `grafana/provisioning/dashboards/json/site-evidence-planning-quality.json`.
- Archived obsolete `grafana/provisioning/dashboards/json/site-evidence-compliance.json` to `grafana/provisioning/dashboards/json/archive/2026-04-30/site-evidence-compliance.json`.
- Added the live `data-trust-ledger` provisioning snapshot and normalized its missing panel units.

## Render System Changes

`scripts/audit-grafana.py` now supports scaled, reliable render passes:

- `--render-workers` for parallel rendering.
- `--render-min-interval` to pace requests and avoid renderer 429s.
- Longer retry/backoff behavior for rate-limited renders.
- `--render-progress` and `--render-progress-every` for long runs.
- `--checkpoint-json`, `--checkpoint-every`, and `--checkpoint-interval` so interrupted full audits can resume without losing successful renders.
- `--resume-json` can be combined with checkpoint output to rerender only unresolved panels.

The normalization helper is `scripts/normalize-grafana-dashboards.py`. It applies the canonical unit, color, label, time-series default, and known SQL fixes across worktree and live dashboard JSON. Run a full render audit after every normalization pass before declaring Grafana changes complete.

## Remaining Work

- Add a formal `make grafana-normalization-audit` wrapper around the current script workflow.
- Add a real sensor/data catalog document or table keyed by `source_table`, `source_column`, `entity_id`, `label`, `unit`, `category`, and `color`. Use `sensor_registry` as the seed, not `verdify_schemas/catalog.py`.
- Add a true wall-clock union stress metric if the site should distinguish “any stress happened this hour” from summed stress-category hours.
