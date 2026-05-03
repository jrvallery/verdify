# Verdify Site Image Audit

Date: 2026-04-28

This audit covers the public Quartz content source at `/mnt/iris/verdify-vault/website` and the served image assets under `website/static/photos`.

## Summary

- Public photo assets after cleanup: 53.
- Markdown image references: 57.
- Unique referenced photos: 41.
- Missing referenced files: 0.
- Archived from public static: the corrupted `roof-camera-exhaust-fan.jpg` contact sheet, `frigate-current.jpg`, `exterior-night-context.webp`, `exterior-night-gazebo-lit.jpg`, and the old `static/verdify-static-backup` tree.

## Editorial Standard

Images should support the core site narrative: a self-improving, AI-enabled, automated solar-powered greenhouse operating under Longmont's high-elevation, dry, seasonal constraints.

Use photos for evidence, not decoration. A photo should show one of these things clearly:

- The physical greenhouse and climate context.
- The growing system and crop state.
- The equipment that senses, actuates, heats, cools, waters, or lights the greenhouse.
- The AI/control loop becoming physical state.

Avoid photos that are only atmospheric, mostly house/patio context, generic plant shots used as crop-specific proof, camera snapshots, contact sheets, or old backups.

## Categories

### Strong Narrative Anchors

These are the best first-impression photos. They clearly communicate the greenhouse, the setting, or the automated growing system.

| File | Contains | Current use | Notes |
|---|---|---|---|
| `exterior-night-snow.jpg` | Greenhouse glowing during snow | Home, greenhouse, structure | Best climate-constraint image. Good homepage anchor. |
| `interior-full-view.jpg` | Full production greenhouse interior | Home | Best indoor counterpart to exterior snow. |
| `interior-production-aisle.jpg` | Aisle, grow lights, hydro channels | Greenhouse overview | Strong production-system photo. |
| `exterior-daytime-side-path.jpg` | Daytime shell, polycarbonate, stone base | Structure | Clean physical structure view. |
| `exterior-evening-patio-wide.jpg` | Greenhouse in patio setting | Structure | Good contextual exterior, but less evidence-dense than snow or side-path. |
| `exterior-dusk-patio.jpg` | Warm exterior at dusk | Climate overview | Useful visual bridge for climate narrative. |

### Growing Evidence

These are useful because they show crops, channels, or propagation stages. They should be used where the page talks about growing, crop targets, or plant outcomes.

| File | Contains | Current use | Notes |
|---|---|---|---|
| `hydro-nft-channels.jpg` | NFT channels with leafy greens | Lettuce, hydroponics, east zone | Strong hydroponic system photo. |
| `hydro-peppers-lettuce-channels.jpg` | Peppers and lettuce in channels | Peppers | Good crop-system evidence. |
| `hydro-strawberry-flowers.jpg` | Strawberry plants flowering | Strawberries | Strong crop-specific evidence. |
| `hydro-strawberry-harvest.jpg` | Strawberry harvest in system | Strawberries | Useful, but composition is close and partially occluded. |
| `seedling-trays-humidity-dome.jpg` | Propagation trays and domes | Growing | Strong propagation-stage evidence. |
| `seedling-flats-propagation.jpg` | Seedling flats under lights | Growing, herbs, basil, east zone | Good generic propagation image. |
| `planters-labeled-starts.jpg` | Labeled starts in blue planters | Cucumbers, tomatoes, west zone | Useful only when discussing starts or labels. Avoid as generic crop proof. |
| `planters-seedlings-mint.jpg` | Blue troughs with seedlings and mint | West zone | Good zone-specific image. |
| `interior-cannas-hydro-growlights.jpg` | Canna lilies, hydro, grow lights | Canna | Good crop-specific image, portrait crop needs controlled display. |
| `vanda-orchids-hanging.jpg` | Hanging Vanda orchids | Orchid, center zone | Good center-zone/crop image. |

### Equipment And Control Evidence

These photos work best on technical pages. Several are portrait orientation or closeups, so they should not be used as full-width hero material.

| File | Contains | Current use | Notes |
|---|---|---|---|
| `control-center-laptop.jpg` | Relay controller plus laptop | Intelligence, planning, controller | Strong "AI/control loop becomes physical" image. |
| `kincony-relay-closeup.jpg` | KinCony relay wiring | Controller, equipment | Good technical evidence. |
| `esp32-controller.jpg` | Controller enclosure | Equipment | Useful but portrait/close composition. |
| `south-wall-fans-misters.jpg` | Exhaust fans, misters, south wall | Greenhouse, cooling, humidity, south zone | Strong equipment and microclimate image. |
| `exhaust-fan-mister-nozzles.jpg` | Fan and mister closeup | South zone | Good close evidence. |
| `motorized-louver-vent.jpg` | Louver vent | Cooling | Useful but portrait/close composition. |
| `lennox-heater-circulation-fan.jpg` | Heater and circulation fan | Heating | Good heating equipment photo. |
| `lennox-heater-overhead.jpg` | Lennox unit heater and vent | Heating | Useful technical closeup. |
| `north-wall-utility-wide.jpg` | North wall utility systems | Equipment | Strong equipment overview. |
| `north-wall-equipment.jpg` | North wall sink/manifold/heater | North zone | Good zone photo. |
| `north-wall-manifold.jpg` | Irrigation manifold | North zone | Good water-control evidence. |
| `north-wall-overview.jpg` | North equipment wall overview | North zone | Useful, portrait orientation. |
| `tzone-sensor-north.jpg` | Tzone sensor | Equipment | Useful sensor evidence, but narrow. |
| `tzone-sensor-south.jpg` | Tzone sensor | Data | Useful sensor evidence, but narrow. |
| `water-flow-meter.jpg` | Pulse-output water meter | Water | Strong water instrumentation photo. |
| `drip-irrigation-emitters.jpg` | Drip emitters in pots | Water | Good irrigation detail. |
| `rinnai-water-heater.jpg` | Water heater | Equipment | Useful, but less central to public story. |

### Physical Structure And Context

These are useful when discussing the greenhouse shell, constraints, and site. Avoid overusing house/patio context on evidence pages.

| File | Contains | Current use | Notes |
|---|---|---|---|
| `jason-and-james.jpeg` | Jason and James inside the greenhouse near controller/equipment wall | About | Strong human-origin hero photo; keep scoped to personal story pages. |
| `exterior-daytime-house-solar.jpg` | Greenhouse beside house and solar | About | Useful for origin/context. More residential than technical. |
| `exterior-winter-snow-lamppost.jpg` | Winter exterior with snow | Climate | Good seasonal constraint image. |
| `exterior-snow-falling-night.jpg` | Snow at night | Heating | Good heating/climate constraint image, duplicates snow theme. |
| `exterior-night-patio-lights.jpg` | Night exterior with lights | Lighting | Useful lighting-context photo. |
| `exterior-night-rain-reflections.jpg` | Rain on patio | Water | Atmospheric; acceptable only as water/climate context. |
| `roof-timber-staghorn-fern.jpg` | Timber roof and fern | Structure | Shows shell details, but visually gray and less clear. |
| `greenhouse-entry-door.jpg` | Entry door and stone wall | Structure | Useful structure detail, portrait and low impact. |

### Available But Unused

These remain in `static/photos` because they may be useful in the next editorial pass. They should not be added casually.

| File | Contains | Recommendation |
|---|---|---|
| `exterior-daytime-side-vent.jpg` | Clean daytime side/vent exterior | Candidate replacement for weaker structure/cooling photos. |
| `exterior-daytime-tree-shade.jpg` | Greenhouse with tree shade | Useful if writing about microclimate/shade. |
| `exterior-dusk-patio-2.jpg` | Alternate dusk patio | Keep as alternate, not needed now. |
| `exterior-dusk-steps-tree.jpg` | Patio steps and greenhouse context | Keep as alternate, less focused. |
| `exterior-patio-trellises-vines.jpg` | Patio/trellis exterior context | Too patio-heavy for primary site use. |
| `exterior-wide-property-solar.jpg` | Wide property and solar context | Useful if solar/power context gets a page. |
| `hydro-peppers-lettuce.jpg` | Alternate hydro crop image | Candidate replacement for pepper/lettuce pages. |
| `interior-aisle-hydro-cannas-wide.jpg` | Dense growing aisle | Strong candidate for greenhouse/growing pages. |
| `interior-orchids-cannas.jpg` | Orchid/canna interior | Candidate for center/crop pages. |
| `interior-orchids-mister-nozzles.jpg` | Orchids and mister context | Candidate for humidity/orchid pages. |
| `kincony-relay-board.jpg` | Relay board closeup | Redundant with `kincony-relay-closeup.jpg`. |
| `relay-boxes-ceiling.jpg` | Ceiling relay boxes/controller | Technical alternate, portrait and less polished. |

## Cleanup Done

- Replaced `intelligence/index.md` image from corrupted `roof-camera-exhaust-fan.jpg` to `control-center-laptop.jpg`.
- Replaced `greenhouse/crops/basil.md` image from generic labeled starts to `seedling-flats-propagation.jpg`.
- Archived non-site or broken public assets under `/mnt/iris/verdify-vault/archive/website-image-cleanup-2026-04-28`.

## Remaining Follow-Ups

- Add crop-specific images for basil, cucumbers, and tomatoes when current plant photos exist. Until then, keep copy honest and avoid implying exact crop proof from generic seedlings.
- Consider a curated image manifest with fields for category, quality, preferred pages, and archive status. This would let `site-doctor` flag accidental use of low-quality or out-of-place photos.
- Consider CSS classes for portrait technical closeups so equipment images render as compact evidence photos instead of page-dominating visuals.
