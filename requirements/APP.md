# Addendum — Crop Management & Observations (UI/UX + Integration)

**Version:** 2.0 (MVP)
**Scope:** Extends the **App Specification for AI‑Powered Greenhouse** with all screens, flows, validations, and integrations for **Crop Catalog**, **Zone Plantings**, and **Observations** (photos, measurements, notes). Fully aligned with Verdify v2.0 invariants (metric units, UTC timestamps, 1:1 active zone↔planting).

---

## 1) Navigation (Updated)

```
Login
 └── Dashboard
     ├── Greenhouses
     │    └── Greenhouse Detail
     │         ├── Controllers
     │         ├── Zones
     │         │    ├── Zone Detail
     │         │    │    ├── Planting (create/end; 1 active)
     │         │    │    └── Observations (list/add/edit)
     │         ├── Sensors & Actuators Mapping
     │         ├── Fan Groups
     │         ├── Buttons
     │         ├── State Machine Grid
     │         ├── Config Publish/Diff
     │         ├── Plans (preview)
     │         └── Telemetry Dashboards
     └── Crop Catalog
          ├── Crop List
          └── Crop Editor (recipe)
```

---

## 2) Crop Catalog

### 2.1 Crop List

**Wireframe**

```
[ Crop Catalog ]          [ + New Crop ]
Search [_________]  Filter: [Tag ▼]  Sort: [Name ▲▼]

| Name        | Growing Days | Yield (kg/m²) | Updated At      | Actions     |
| Tomato      | 90           | 6.0           | 2025-08-10Z     | [Edit]      |
| Lettuce     | 45           | 3.2           | 2025-08-01Z     | [Edit]      |
```

**API**

* `GET /crops?search=&page=&page_size=`

  * Response: list of `crop` (id, name, description, expected\_yield\_per\_sqm, growing\_days, recipe).

**AC**

* Debounced search; pagination 25/50/100; empty state guidance.

### 2.2 Crop Editor

**Wireframe**

```
[ New/Edit Crop ]
Name * [ Tomato ]
Description [ text... ]
Expected Yield (kg/m²) [ 6.0 ]
Growing Days [ 90 ]

Recipe (staged) 
[ + Add Stage ]
Stage Card:
  stage_id [veg]  Label [Vegetative]
  day_range: Start [10] End [45]
  Targets:
    temp_min_c [20.0]  temp_max_c [26.0]
    vpd_min_kpa [0.6]  vpd_max_kpa [1.2]
    photoperiod_h [16]           (if lights present)
    soil_vwc_min [0.25] (m³/m³)  soil_vwc_max [0.40]
  Irrigation hints:
    duration_s [300]  min_interval_min [180]
  Notes [ text... ] 
[ Save ]
```

**Validation**

* Required: `name`.
* `growing_days >= 1`.
* Each stage: `0 ≤ start_day < end_day ≤ growing_days`.
* Stage ranges **must not overlap** and **should** cover 0..growing\_days (not mandatory for MVP).
* `min ≤ max` for all targets.
* All values metric.

**API**

* Create: `POST /crops`
* Update: `PATCH /crops/{id}`
* Payload (excerpt):

```json
{
  "name": "Tomato",
  "description": "Indeterminate greenhouse tomato",
  "expected_yield_per_sqm": 6.0,
  "growing_days": 90,
  "recipe": {
    "stages": [
      {
        "stage_id": "seedling",
        "label": "Seedling",
        "start_day": 0,
        "end_day": 14,
        "targets": {
          "temp_min_c": 21.0, "temp_max_c": 24.0,
          "vpd_min_kpa": 0.4,  "vpd_max_kpa": 0.8,
          "photoperiod_h": 16
        },
        "irrigation": { "duration_s": 120, "min_interval_min": 240 },
        "notes": "Avoid overwatering."
      }
    ]
  }
}
```

**AC**

* JSON editor available (advanced) + guided forms (default).
* Server errors mapped inline (overlapping stages, invalid ranges).

---

## 3) Zones & Plantings (Expanded)

### 3.1 Zone Detail (expanded section)

**Wireframe**

```
Zone Detail: Zone #1 (NE)
Context for Planner [textarea]
Active Planting
  [ Start Planting ] if none
  else: Crop: Tomato | Started: 2025-08-01 | Area (m²): 4.0
        [ View Planting ] [ End Planting ]
Observations
  [ Add Observation ]  [ View All ]
```

**API**

* Zone read/update: `GET /zones/{id}`, `PATCH /zones/{id}`
* Planting list: `GET /zone_crops?zone_id={id}&is_active=true`
* Start planting: `POST /zone_crops`
* End planting: `PATCH /zone_crops/{id}` `{ "end_date": "...Z", "is_active": false, "final_yield": 5.8 }`

**Validation**

* **Invariant:** **1 active planting per zone** (server‑enforced).
* `area_sqm ≥ 0`.
* `final_yield ≥ 0` when ending.

**AC**

* “Start Planting” disabled if an active planting exists.
* Ending requires confirmation; success updates UI immediately.

### 3.2 Start Planting Wizard

**Flow**

1. Select Crop (from catalog; searchable).
2. Set Start Date (default today, UTC), Area (m²), optional notes.
3. Confirm summary.

**Wireframe**

```
[ Start Planting ]
Step 1: Select Crop [ Tomato ▼ ]
Step 2: Start Date [ 2025-08-12 ]  Area (m²) [ 4.0 ]
Notes [text...]
[Start]
```

**API**

```json
POST /zone_crops
{
  "zone_id":"<uuid>",
  "crop_id":"<uuid>",
  "start_date":"2025-08-12T00:00:00Z",
  "area_sqm":4.0,
  "is_active":true
}
```

**AC**

* If zone already has an active planting, server returns `409 E409_CONFLICT`; show inline error.

### 3.3 Planting Detail View

**Wireframe**

```
Planting: Tomato in Zone #1
Started: 2025-08-01 (Day 11 of 90)  |  Current Stage: Seedling (0–14)
Recipe Targets (current stage)
  Temp: 21.0–24.0 °C  |  VPD: 0.4–0.8 kPa  |  Photoperiod: 16 h
Irrigation hints: duration 120 s, ≥240 min
[ View Recipe ]  [ Add Observation ]  [ End Planting ]
Observations (recent)
  | Date (UTC)              | Height cm | Health | Notes |
  | 2025-08-11T17:00:00Z    |  8.0      | 7      | ...   |
  [ View All ]
```

**API**

* `GET /zone_crops/{id}`
* `GET /observations?zone_crop_id={id}&limit=10`

**AC**

* “Current Stage” uses `days_since_start` vs recipe. If recipe missing, show “—”.

---

## 4) Observations

### 4.1 Observations List (Zone or Planting context)

**Wireframe**

```
Observations — Zone #1 / Planting Tomato
Filters: Date Range [ ], Health [1..10], Has Photo [ ]  [Apply]
[ + Add Observation ]

| Observed At (UTC)        | Height cm | Health | Photo | Notes        | Actions |
| 2025-08-11T17:00:00Z     | 8.0       | 7      | [🖼️]  | tip burn...  | [View]  |
```

**API**

* `GET /observations?zone_crop_id=...&start=...&end=...&min_health=&max_health=&has_photo=`

**AC**

* Pagination with infinite scroll or pages.
* Thumbnails lazy-loaded.

### 4.2 Add/Edit Observation

**Wireframe**

```
[ Add Observation ]
Observed At (UTC) [ now ]   (datetime)
Height (cm) [ ]              (≥0)
Health (1–10) [ 7 ]          (integer)
Photo [ Upload ] [ or paste URL ] 
Notes [textarea 2000 chars]
[ Save ]
```

**Validation**

* `health_score` integer 1..10.
* `height_cm ≥ 0` (optional).
* `observed_at` ISO 8601 Z.
* If using upload, file ≤ 10 MB, JPEG/PNG. (UI‑side; server stores `image_url` only.)

**Upload Flow (preferred)**

1. `POST /media/presign` (if available) → `{ upload_url, public_url, headers }`
2. `PUT` file to `upload_url` with `headers`.
3. `POST /observations` with `image_url=public_url`.

**API (MVP minimal if presign not ready)**

* `POST /observations`

```json
{
  "zone_crop_id":"<uuid>",
  "observed_at":"2025-08-12T18:00:00Z",
  "height_cm":12.3,
  "health_score":7,
  "image_url":"https://cdn.example/obs/abc.jpg",
  "notes":"Leaves perked up after watering."
}
```

**AC**

* Preview image before save.
* Shows upload progress; retries allowed.
* Server errors mapped inline (`E422_VALIDATION`, etc.).

### 4.3 Observation Detail

**Wireframe**

```
Photo [large preview if present]
Observed At: 2025-08-12T18:00:00Z
Height: 12.3 cm  |  Health: 7/10
Notes:
  Leaves perked up...
[ Edit ] [ Delete ]
```

**API**

* `GET /observations/{id}`
* `PATCH /observations/{id}`
* (Optional) `DELETE /observations/{id}` (soft delete or hard delete per backend policy)

**AC**

* Back link to planting.
* Confirmation on delete.

---

## 5) Data Mapping (App ⇄ API)

### 5.1 Crop (create/update)

```json
{
  "name":"Tomato",
  "description":"Indeterminate GH tomato",
  "expected_yield_per_sqm":6.0,
  "growing_days":90,
  "recipe":{
    "stages":[
      {
        "stage_id":"seedling",
        "label":"Seedling",
        "start_day":0,"end_day":14,
        "targets":{
          "temp_min_c":21.0,"temp_max_c":24.0,
          "vpd_min_kpa":0.4,"vpd_max_kpa":0.8,
          "photoperiod_h":16
        },
        "irrigation":{"duration_s":120,"min_interval_min":240},
        "notes":"Avoid overwatering."
      }
    ]
  }
}
```

### 5.2 Zone Planting (start)

```json
{
  "zone_id":"<uuid>",
  "crop_id":"<uuid>",
  "start_date":"2025-08-12T00:00:00Z",
  "area_sqm":4.0,
  "is_active":true
}
```

### 5.3 Observation (add)

```json
{
  "zone_crop_id":"<uuid>",
  "observed_at":"2025-08-12T18:00:00Z",
  "height_cm":12.3,
  "health_score":7,
  "image_url":"https://cdn.example/obs/abc.jpg",
  "notes":"Leaves perked up."
}
```

---

## 6) Validation & Error Mapping

| Case                             | Validation                                | API Error         | UI Handling                                    |
| -------------------------------- | ----------------------------------------- | ----------------- | ---------------------------------------------- |
| Overlapping recipe stages        | `end_day > start_day`, ranges non‑overlap | `E422_VALIDATION` | Stage card highlights offending fields         |
| Zone already has active planting | 1 active per zone                         | `E409_CONFLICT`   | Modal error with link to end existing planting |
| Observation health out of range  | `1..10`                                   | `E422_VALIDATION` | Inline error                                   |
| Image too large                  | ≤10MB (client)                            | —                 | Block upload; show helper                      |

---

## 7) Examples & Wireframe Snippets

**Crop stage card (ASCII form)**

```
+---------------- Stage: Vegetative ----------------+
| Days: 10..45                                      |
| Temp °C: 20.0 .. 26.0     VPD kPa: 0.6 .. 1.2     |
| Photoperiod (h): 16       Soil VWC: 0.25 .. 0.40  |
| Irrigation: dur 300 s / ≥180 min                  |
| Notes: [_______________________________]          |
+---------------------------------------------------+
```

---

## 8) Tests & Acceptance Criteria (E2E)

1. **Create Crop with Valid Stages**

   * AC: POST succeeds; list shows crop; reload persists.

2. **Reject Overlapping Stages**

   * AC: Server returns `E422_VALIDATION`; UI highlights overlaps.

3. **Start Planting in Empty Zone**

   * AC: POST creates active planting; Zone Detail shows summary.

4. **Prevent Second Active Planting**

   * AC: POST returns `E409_CONFLICT`; UI displays resolution guidance.

5. **Add Observation with Photo**

   * AC: Upload via presign (or direct URL) + POST; list shows thumbnail; detail page renders photo.

6. **Edit Observation**

   * AC: PATCH updates fields; history reflects updated values.

7. **End Planting**

   * AC: PATCH sets `end_date`, `is_active=false`; Zone shows “Start Planting” again.

8. **Planner Context Surface**

   * AC: Zone/Greenhouse `context_text` visible/editable; saved. (Used by Planning; view-only confirmation note.)

---

## 9) Risks & Edge Cases

* **Missing recipe:** Planting detail still functions; stage shown as “—”; observations unaffected.
* **Time zones:** UI shows local; payloads/tables use UTC Z; date pickers clarify that midnight saves as `T00:00:00Z`.
* **Uploads:** If presign endpoint not available in MVP, use URL paste; ensure CORS for CDN images.
* **Large image files:** Recommend client‑side downscale before upload.
* **Mobile data entry:** Optimize forms for one‑hand use; large inputs and buttons.

---

## 10) Implementation Guidance for Agentic Coder

**Task 1 — Crop Catalog**

* Build Crop List (search, paginate); Crop Editor with stage cards + JSON editor.
* Integrate `GET/POST/PATCH /crops`.
* Tests: create/update; invalid overlap.

**Task 2 — Zone Planting**

* Zone Detail: show active planting or “Start Planting”.
* Implement Start Planting wizard; End Planting flow.
* Integrate `/zone_crops` endpoints.
* Tests: 1 active invariant; end & reopen.

**Task 3 — Observations**

* List + filters; Add/Edit forms; Detail page.
* Image upload: presign flow if available; else URL paste.
* Integrate `/observations` endpoints.
* Tests: health/height validation; image preview; pagination.

**Task 4 — Integration & UX Polish**

* Planting Detail computes “Day N” and “Current Stage” from recipe.
* Link observations from telemetry dashboards (date cross‑filters).
* Accessibility pass: labels, keyboard, ARIA.

**Dependencies**

* Backend endpoints from API spec; optional `/media/presign`.
* CDN/storage for images (or placeholder).

---

## 11) Self Check List

* [x] Navigation updated to include Crop Catalog, Planting, Observations.
* [x] All screens have wireframes, fields, validations, APIs, AC.
* [x] Recipe stage model aligns with backend JSON (metric, UTC).
* [x] Zone↔Planting 1:1 active enforced via UI and error handling.
* [x] Observation upload + forms defined; health/height rules included.
* [x] Examples provided for Crop, Planting, Observation JSON.
* [x] End‑to‑end tests specified for all key flows.
