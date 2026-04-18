---
title: Hydroponics
tags: [greenhouse, hydroponic, nutrients, yinmik, sensors]
date: 2026-04-18
aliases:
  - greenhouse/hydroponics
  - hydro
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">
<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Hydroponics

A 60-position recirculating NFT system on the east wall. **Newly relaunched 2026-04-17** — the meter was calibrated, a fresh probe went in, and the first real crop was planted. Everything on this page dates from that relaunch forward. Measurements from before 2026-04-18 were either pre-calibration noise or recorded in the wrong units, so they have been zeroed out of the database. Don't trust any chart that shows hydro data older than the cutoff.

![Hydroponic NFT channels in the east zone](/static/photos/hydro-nft-channels.jpg)

## The System

- **Location**: East zone — the coolest microclimate in the greenhouse (peak ~91°F vs 100°F+ in south). Best match for leafy greens and berry crops that bolt in heat.
- **Layout**: 3 PVC NFT rails × 2 rows (top: positions 1–30, bottom: 31–60). 60 positions total.
- **Media**: Grodan rockwool cubes in net cups, clay pellet ballast.
- **Lighting**: 14× Barrina 2FT LED grow lights at 12" spacing directly overhead. See [Lighting](/climate/lighting/) for DLI context.
- **Nutrients**: General Hydroponics Flora series (FloraMicro / FloraGro / FloraBloom).
- **Reservoir heat**: Rinnai RE140iN tankless — holds nutrient solution around 74–76°F.

## Live Monitoring

The **YINMIK multi-parameter meter** sits submerged in the reservoir and reports every few minutes via Home Assistant. Six metrics flow into Verdify:

<div class="grafana-controls" data-ranges="6h,24h,7d,30d"></div>

<div class="pg s2">
<iframe src="https://graphs.verdify.ai/d-solo/greenhouse-hydroponics/?orgId=1&panelId=4&theme=dark" width="100%" height="300" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/greenhouse-hydroponics/?orgId=1&panelId=2&theme=dark" width="100%" height="300" frameborder="0"></iframe>
</div>

<div class="pg s2">
<iframe src="https://graphs.verdify.ai/d-solo/greenhouse-hydroponics/?orgId=1&panelId=3&theme=dark" width="100%" height="300" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/greenhouse-hydroponics/?orgId=1&panelId=5&theme=dark" width="100%" height="300" frameborder="0"></iframe>
</div>

<div class="pg s1">
<iframe src="https://graphs.verdify.ai/d-solo/greenhouse-hydroponics/?orgId=1&panelId=1&theme=dark" width="100%" height="300" frameborder="0"></iframe>
</div>

Full dashboard with all panels + reservoir status: [graphs.verdify.ai/d/greenhouse-hydroponics](https://graphs.verdify.ai/d/greenhouse-hydroponics).

## Target Ranges

| Metric | Target | Why |
|---|---|---|
| **pH** | 5.5 – 6.5 | The sweet spot where all macro- and micronutrients stay soluble. Drifts up as plants consume nitrates and hydroxides accumulate. |
| **EC** | 800 – 1,800 µS/cm | Solution strength. Seedlings want ~400–600, vegetative growth 800–1,200, fruiting 1,200–1,800. Higher ≠ better — high EC at seedling stage burns roots. |
| **TDS** | 400 – 1,000 ppm | Tracks EC (roughly EC × 0.5). Redundant check against EC drift. |
| **Water temp** | 60 – 75°F | Below 60 slows nutrient uptake. Above 75 drops dissolved oxygen and breeds pythium and other pathogens. |
| **ORP** | 200 – 400 mV | Oxidation-reduction potential — measures the antimicrobial state of the solution. Low ORP suggests biofilm or organic buildup. |
| **Battery** | > 20% | The YINMIK runs on an internal battery. Drops below 20% mean a charge is due before readings get noisy. |

## Data Path

The YINMIK uses a Tuya Bluetooth backend that encodes some metrics in non-standard scalings (pH as raw × 400, TDS as raw × 0.5, EC as raw × 0.565). Home Assistant applies the empirical corrections via template sensors in `/config/packages/greenhouse/hydroponic_calibration.yaml`. Verdify's ingestor then reads the `_corrected` entities every 5 minutes via the Home Assistant REST API.

```
YINMIK meter
   │  Bluetooth → Tuya DPs (raw, non-standard scaling)
   ▼
Home Assistant LocalTuya
   │  template sensors apply: pH ÷ 400, TDS × 2.0, EC × 1.77
   ▼
Verdify ingestor (tasks.py:_HYDRO_MAP, every 300s)
   │  writes to climate.hydro_* columns
   ▼
TimescaleDB → Grafana dashboard → this page
```

Water temp, ORP, and battery don't need the correction shim — their DPs report in sensible units directly.

## What's Not Monitored (Yet)

Honesty section — these gaps matter for decision-making and are explicitly not covered:

- **Dissolved oxygen (DO)**: the most important missing measurement. A failing air pump or biofilm crash would not be visible until plant symptoms appeared. On the P1 sensor roadmap.
- **Water level**: no float switch or pressure reading on the reservoir. A leak or evaporation drift is noticed visually, not automatically.
- **Inline pH/EC (Atlas Scientific)**: the YINMIK is a single-point submerged probe. It doesn't see differences between the reservoir and what the roots actually experience at the end of a long NFT channel. On the roadmap.
- **Per-zone runoff pH/EC**: for soil drip systems, runoff pH reveals root-zone conditions; currently not measured at the center or wall drip outlets.

## Ties to the Broader System

- The hydroponic reservoir shares the same **east-zone air sensor** used for the climate band. VPD and temp control for the east zone apply equally to the crops in the NFT — see [Zones → East](/greenhouse/zones/east/).
- Water for the reservoir comes from the same line as the [misting and drip systems](/climate/water/). A mister lockout or [leak event](/greenhouse/equipment/) can share root cause with a reservoir fill anomaly.
- When the planner enters a ventilation or dehumidification mode, the reservoir temperature lags indoor air by hours. Nutrient solution thermal mass is a lever, not a noise source.

---

*Relaunched 2026-04-18. First legitimate data point: 2026-04-18 19:04 UTC, pH 6.21, EC 2,478 µS/cm, TDS 1,248 ppm, water temp 74.7°F.*
