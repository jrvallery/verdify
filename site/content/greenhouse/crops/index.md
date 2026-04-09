---
title: Crop Profiles
tags: [crops, reference, greenhouse]
date: 2026-04-08
---

# Crop Profiles

Each crop has a 24-hour diurnal profile that defines what temperature and VPD it needs at each hour. The tightest envelope across all active crops in a zone becomes the setpoint the ESP32 enforces. When you change what's planted, the control targets change automatically.

## Active Crops

| Crop | Zone | System | VPD Sensitivity | Profile |
|------|------|--------|----------------|---------|
| [Lettuce](lettuce) | East | Hydro | High (bolts above 80F) | [Profile](lettuce#diurnal-target-profile-spring) |
| [Strawberry](strawberries) | East | Hydro | High | [Profile](strawberries#diurnal-target-profile-spring) |
| [Pepper](peppers) | East | Hydro | Moderate | [Profile](peppers#diurnal-target-profile-spring) |
| [Basil](basil) | East | Hydro | Moderate | [Profile](basil#diurnal-target-profile-spring) |
| [Vanda Orchids](vanda-orchids) | Center | Mounted | Very high (low VPD ceiling) | [Profile](vanda-orchids#diurnal-target-profile-spring) |
| [Canna Lilies](canna-lilies) | South | Soil | Very low (tolerates dry air) | [Profile](canna-lilies#diurnal-target-profile-spring) |

## Reference Crops (not currently planted)

| Crop | Best Zone | Notes |
|------|-----------|-------|
| [Cucumbers](cucumbers) | West | Warm-season, vigorous vining |
| [Tomatoes](tomatoes) | South | Needs highest DLI, tolerates heat |
| [Herbs](herbs) | East/West | Depends on species |

## How Crop Profiles Drive Control

The band function (`fn_band_setpoints`) reads the crop profiles for the current hour and computes the composite target: the tightest range that keeps ALL active crops comfortable. This band becomes the ESP32's temp_high, temp_low, vpd_high, vpd_low setpoints, updated every 5 minutes.

Per-zone VPD targets (`fn_zone_vpd_targets`) take this further: each zone's mister target comes from the specific crops planted there. The firmware's stress-score algorithm picks the most stressed zone for each mist pulse.
