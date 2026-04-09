---
title: "The Greenhouse"
tags: [greenhouse, overview]
date: 2026-03-28
---

# The Greenhouse

367 sq ft at 5,090 feet. Six polycarbonate walls create natural light and temperature gradients across the space. At peak sun, the south zone runs 9F hotter than the east. That stratification is an asset: match crops to their microclimate rather than pretending the room is uniform. 172 sensors and an ESP32 running 42 climate states every 5 seconds.

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin: 2rem 0;">
<div>

![Greenhouse exterior at night during snowfall](/static/photos/exterior-night-snow.jpg)

The hexagonal shape isn't decorative |â|€|” it's structural. Six walls at varying angles to the sun create natural light and temperature gradients that we exploit for crop placement. The south wall catches peak solar noon. The southwest angle gets 23.5% light transmission |â|€|” the best in the building.

</div>
<div>

![Production aisle with LED grow bars and hydroponic channels](/static/photos/interior-production-aisle.jpg)

Inside: hydroponic NFT channels on the east wall, six shelf bays on the west, floor pots in the south, and 49 grow lights across two circuits. The concrete slab stores solar heat during the day and releases it overnight |â|€|” free heating in winter, a liability in summer.

</div>
</div>

## Three Microclimates in 367 Square Feet

At any given moment, there can be a **9|Â|°F difference** between the hottest and coolest zones. That stratification is not just a challenge, it is an asset. It lets us match crops to the conditions they actually want instead of pretending the room is uniform.

| Microclimate | Zones | Character |
|-------------|-------|-----------|
| **Hot + Dry** | [[greenhouse/zones/south|South]] | Peak solar, nearby exhaust path, 100|Â|°F+ at noon. Peppers and tomatoes. |
| **Cool + Humid** | [[greenhouse/zones/east|East]] | Tree shade, patio door, hydro evaporation. Lettuce and strawberries. |
| **Moderate** | [[greenhouse/zones/west|West]] | Longest wall, versatile. Herbs, starts, cucumbers. |

â|†|’ [[greenhouse/zones/|All five zones]] including [[greenhouse/zones/north|North]] (equipment) and [[greenhouse/zones/center|Center]] (offline).

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin: 2rem 0;">
<div>

![South end |â|€|” exhaust fans on the angled faces, mister nozzles, and climate sensors](/static/photos/south-wall-fans-misters.jpg)

</div>
<div>

## The Defining Tension

The [[greenhouse/structure|glazing]]'s SHGC (0.66) exceeds its visible light transmission (0.57) |â|€|” the greenhouse admits proportionally more solar heat than visible photosynthetic light. Across ~785 sq ft of glazed surface, peak solar gain reaches 65,000-87,000 BTU/hr. Fan cooling is powerful (4,900 CFM, 13+ CFM/sq ft) but cannot cool below ambient |â|€|” and at 5,090 ft altitude, air carries 17% less thermal mass than at sea level.

You can't software your way past that on a 90F day. External shade cloth on the roof and WSW wall is the single most impactful improvement possible. We don't have it yet.

</div>
</div>

<div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; margin: 2rem 0;">

![Canna lilies blooming beside hydroponic channels under grow lights](/static/photos/interior-cannas-hydro-growlights.jpg)

![Strawberry flowers in the hydroponic system](/static/photos/hydro-strawberry-flowers.jpg)

![Orchids and mister nozzles on the shelving wall](/static/photos/interior-orchids-mister-nozzles.jpg)

</div>

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1rem 0;">

![Daytime exterior |â|€|” the greenhouse side with louvered vent and polycarbonate panels](/static/photos/exterior-daytime-side-vent.jpg)

![Exterior patio with trellised vines and the greenhouse behind](/static/photos/exterior-patio-trellises-vines.jpg)

</div>

## Dive Deeper

- [[greenhouse/structure|Physical Structure]] |â|€|” dimensions, glazing, thermal envelope, light transmission
- [[greenhouse/zones/|Growing Zones]] |â|€|” detailed microclimate profiles for each zone
- [[greenhouse/equipment|Equipment]] |â|€|” every mechanical, electrical, and sensing component
- [[greenhouse/growing|Growing & Crops]] |â|€|” what we grow, where, and why |â|€|” hydro, soil, crop profiles
