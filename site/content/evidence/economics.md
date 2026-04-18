---
title: Economics
tags: [evidence, economics, cost, solar, tesla]
date: 2026-04-07
type: canonical
currency: USD
electric_rate_kwh: 0.111
electric_source: solar_self_generation
aliases:

  - economics
gas_rate_therm: 0.83
water_rate_gal: 0.00484
avg_daily_cost: 4.28
solar_aligned_pct: 62.6
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Economics
Verdify is not just trying to keep plants alive. It is trying to do that in a way that respects energy, water, timing, and the physical reality of a solar-powered household greenhouse.
This is the canonical economics page for the site.
The greenhouse costs about **$4.28 per day** on average to run. January can climb to roughly **$270 per month** when gas heating dominates. August can fall to about **$20 per month**. Those swings are not side trivia. They are part of the operating problem Verdify is built to solve.

## What this page should answer
1. What does the greenhouse actually cost to run?
2. Which utility streams matter most in each season?
3. How much of the electrical load aligns with solar production?
4. Which control decisions are cheap, and which are expensive?
5. Why does cost-aware control matter without turning the site into a utility report?

## Why economics belong in the product story
The greenhouse sits on a home with rooftop solar and Tesla Powerwalls. That creates a real asymmetry:

- daytime electrical loads can align with solar production
- nighttime electrical loads can lean on storage
- natural gas remains the main winter heating cost
That means the same control action can have very different economics depending on when it happens.
Verdify is interesting partly because it is not optimizing in a vacuum. It is making real tradeoffs inside a physical system with measured costs.

## Live cost proof

<div class="grafana-controls" data-ranges="7d,30d,60d,90d,1y"></div>

<div class="pg s3">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=301&theme=dark" width="100%" height="140" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=304&theme=dark" width="100%" height="140" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=305&theme=dark" width="100%" height="140" frameborder="0"></iframe>

</div>

<div class="pg s3">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=302&theme=dark" width="100%" height="140" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=303&theme=dark" width="100%" height="140" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=306&theme=dark" width="100%" height="140" frameborder="0"></iframe>

</div>
More than **60% of greenhouse electrical demand** lands during strong solar-production hours. That is one of the cleanest proof points on the site. The greenhouse is not merely electrified. Its heaviest electrical work tends to happen when the house is best positioned to support it.

## The cost structure
The greenhouse has three utility streams:

- **electricity** for fans, fog, grow lights, controller hardware, and pumps
- **natural gas** for the Lennox furnace
- **water** for misting, irrigation, [hydroponics](/greenhouse/hydroponics/), and humidity control
That means Verdify is balancing at least three things at once:

- plant stress
- operating cost
- timing relative to solar production
This is why economics belong under proof, not under a generic sustainability label. The point is not moral branding. The point is measured operating behavior.

## By circuit and by cost

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=311&theme=dark" width="100%" height="320" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=312&theme=dark" width="100%" height="320" frameborder="0"></iframe>

</div>

<div class="pg s4">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=201&theme=dark" width="100%" height="140" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=202&theme=dark" width="100%" height="140" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=203&theme=dark" width="100%" height="140" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=204&theme=dark" width="100%" height="140" frameborder="0"></iframe>

</div>
These are measured costs, not marketing estimates. Electric is tracked at **$0.111/kWh**, gas at **$0.83/therm**, and water at **$0.00484/gal**.

## The winter gas constraint
Solar helps with electric loads. It does not erase the winter gas problem.
The **75,000 BTU Lennox furnace** is the dominant winter operating cost. It is also far more cost-effective per BTU than the small electric heater. That is why Verdify stages electric heat first for mild dips and brings gas in for heavier work.

| Month | Electric | Gas | Water | Total |
|-------|----------|-----|-------|-------|
| August | $7 | $2 | $11 | **$20** |
| January | $90 | $176 | $4 | **$270** |
| March | $51 | $62 | $9 | **$122** |
This is the kind of tradeoff the site should make legible. Cost-aware control is not about minimizing spend at all costs. It is about understanding which resource is doing the work, when, and why.

## Cost-aware control
The planner does not optimize for cost first. Plant health comes first.
But when two strategies produce similar plant outcomes, Verdify should prefer the cheaper one. That means questions like these are part of every planning cycle:

- when is electric heat acceptable because solar is covering it?
- when is gas the better tool because the BTU economics are overwhelmingly better?
- when is fog worth its 1,644W draw because it avoids hours of VPD stress?
- when are grow lights effectively low-cost because the Powerwalls are full and solar is abundant?
That is the real economics story. Not just what the greenhouse costs, but how intelligence changes the meaning of those costs.

## Long-range proof

<div class="pg s1">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=13&theme=dark" width="100%" height="400" frameborder="0"></iframe>

</div>

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=9&theme=dark" width="100%" height="320" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=2020&theme=dark" width="100%" height="320" frameborder="0"></iframe>

</div>

<div class="pg s1">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-economics/?orgId=1&panelId=10&theme=dark" width="100%" height="320" frameborder="0"></iframe>

</div>

## Bottom line
The numbers are simple enough to say plainly:

- about **$4.28/day** average
- about **$1,564/year**
- about **62.6% solar alignment** on electric load
- gas dominates winter cost
- water matters operationally more than financially
That is why this page belongs in the proof layer. It shows that Verdify is not just technically interesting. It is operating inside real resource constraints, with measurable consequences.
If you want the live operational state, go to [[evidence/operations|Operations]].
If you want the broader dashboard directory, go to [[evidence/dashboards|Dashboards]].
[Open Solar Dashboard ↗](https://graphs.verdify.ai/d/site-evidence-economics/) · [Open Cost Dashboard ↗](https://graphs.verdify.ai/d/site-evidence-economics/)
