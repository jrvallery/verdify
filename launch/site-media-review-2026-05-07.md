# Verdify Site Media Review - 2026-05-07

## Summary

Processed the new launch media drop for public website use. The site now uses display-sized JPEGs under `website/static/photos/` and full-resolution, metadata-stripped JPEGs under `website/static/photos/full/` for selected images that benefit from click-through detail.

## Usable New Sources

| Source | Output | Description | Placement |
|---|---|---|---|
| `/mnt/iris/photos/server_rack.jpeg` | `homelab-cortex-server-rack.jpg` | Portrait view of the Cortex home-lab server rack: stacked compute nodes in a black open rack, visible cooling fans, cabling, and the "My Other Computer Is An Azure Data Center" sticker. This visually anchors the local inference story without showing credentials. | `/intelligence/inference/`, `/intelligence/`, `/ai-greenhouse/` |
| `/mnt/iris/photos/new/20240102_222427571_iOS.heic` | `interior-canna-geranium-path.jpg` | Wide interior greenhouse aisle: red geraniums on the left, canna lilies and yellow flowers in the foreground, seed trays, NFT hydroponic channels, grow lights, overhead plumbing, and the north service wall in the background. Strong launch image because it shows plants and infrastructure together. | `/`, `/greenhouse/`, `/intelligence/`, `/ai-greenhouse/` |
| `/mnt/iris/photos/north wall 2.jpeg` | `north-wall-service-core.jpg` | Straight-on north wall service core: Lennox heater, motorized intake vent, round duct, copper irrigation manifold, solenoid assemblies, stainless utility sink, Rinnai water heater, house-side access, and utility pump. Better explanatory image than the prior north wall crop. | `/greenhouse/equipment/`, `/greenhouse/zones/north/` |

## Unusable New Sources

The following files in `/mnt/iris/photos/new` are currently zero bytes, so ImageMagick cannot decode them:

- `20220711_214839_0BAA1DC1.HEIC`
- `20231217_221303_2DBB0E4C.heic`
- `20231223_020530_57A8863F.heic`
- `20231224_221311_E4560546.heic`
- `20240101_192737570_iOS.heic`
- `54518DF0-0052-4226-851B-96528D14E165.heic`

These look like incomplete Synology/iCloud-style placeholders rather than valid HEIC payloads. Re-copying those originals should make them processable.

## Media Pattern

Use this pattern for important photos:

```html
<figure class="media-figure">
  <a href="/static/photos/full/example.jpg" aria-label="Open full-resolution example photo">
    <img src="/static/photos/example.jpg" alt="Specific, factual description" loading="lazy">
  </a>
  <figcaption>Short explanatory caption that ties the image to the page argument.</figcaption>
</figure>
```

Use `media-grid media-grid-2` or `media-grid media-grid-3` when the images are evidence for the same section. Keep ordinary Markdown images for incidental visual support.
