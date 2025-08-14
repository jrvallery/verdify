# APP.md — Verdify Greenhouse App

**Functional requirements & UI/UX specification aligned to API v2.0 (OpenAPI 3.1)**

**Version:** 2.0
**Target Users:** Growers (operators), Admins (config/controls), and Lab/Dev (device debug)
**Scope:** This document specifies every end‑user screen/flow required to cover the *entire* API surface defined in **Project Verdify MVP API v2.0**, including: authentication, device onboarding, CRUD for greenhouses/zones/controllers/sensors/actuators/fan groups/buttons/state machine rows/fallback; crops/zone‑crops/observations; plans; config publish/diff; meta/health; and developer‑tools for telemetry ingestion and device‑token debugging. It also specifies grower‑facing dashboards and historical analytics (UI contracts defined here; data retrieval will be implemented via internal services outside the current OpenAPI).

---

## 0) Product principles & invariants

* **Safety first:** UI enforces allowable ranges and enumerations defined by the API; destructive actions require confirmation.
* **Single source of truth:** All configuration persists via API calls; local client state is transient.
* **Metric units on wire/UI:** Temperatures in °C, VPD in kPa, lengths in cm/m, areas in m².
* **UTC on wire; local in UI:** All times are stored/sent as ISO‑8601 UTC (`...Z`) and shown in user local time with a UTC toggle.
* **Staging grid semantics:** Temperature and humidity *stages* are integers in `[-3..+3]`, where negatives mean demand (heat/humidify) and positives mean relief (cool/dehumidify).
* **Zone↔Planting invariant:** At most 1 *active* planting (`zone-crops.is_active=true`) per zone.
* **ETag‑aware operations:** Config/plan viewers display current ETags and conditional request semantics where applicable.

---

## 1) Information Architecture & Navigation

```
Auth
 ├── Login
 ├── Register
 └── Logout

Dashboard
 ├── Overview (KPIs + alerts)
 ├── Analytics (history; trends; comparisons)
 └── System Health

Greenhouses
 ├── List / Create
 └── Detail
      ├── Summary & Context
      ├── Zones
      │    ├── List / Create
      │    └── Zone Detail
      │         ├── Active Planting / History
      │         ├── Observations (list/create/edit/detail)
      │         └── Telemetry cross-links (analytics)
      ├── Controllers
      │    ├── List / Create
      │    └── Controller Detail
      │         ├── Token management (rotate/revoke)
      │         ├── Sensors (list/create/edit)
      │         ├── Actuators (list/create/edit)
      │         ├── Fan Groups (list/create, members add/remove)
      │         ├── Buttons (manual override config)
      │         └── Device Debug (view plan/config as device via pasted token)
      ├── State Machine Grid (49 cells + fallback)
      ├── Config Publish & Diff
      └── Plans (list/create/view payload)

Crops
 ├── Catalog (list/create/edit)
 └── Recipes (staged targets, optional)

Plantings
 └── Per-zone Start/End + detail (also accessible from Zone Detail)

Observations
 └── List (filters) / Create / Edit / Detail

Onboarding
 └── Claim Controller (device_name + claim_code)

Meta & Diagnostics
 ├── Sensor/Actuator Kinds
 └── API Health

Developer Tools (Lab-only)
 ├── Telemetry Uploader (sensors/actuators/status/inputs/batch)
 └── Device-Token Viewers (config/plan by-name/me)

Help & About
```

---

## 2) Authentication & Sessions (API tag: **Authentication**)

### 2.1 Login

* **Endpoint:** `POST /auth/login` (no auth, optional `X-CSRF-Token`)
* **Form:** email, password.
* **Success:** Store `access_token` (bearer).
* **Errors:** `401` → inline error “Invalid email or password.”
* **Logout:** `POST /auth/revoke-token` (bearer).

### 2.2 Register

* **Endpoint:** `POST /auth/register` (no auth, optional `X-CSRF-Token`)
* **Form:** email\*, password\* (min 8), full\_name (optional).
* **Success:** Auto‑login using returned `access_token`.
* **Errors:** `409` email exists; `422` invalid email format.

### 2.3 CSRF for browsers

* **Endpoint:** `GET /auth/csrf`
* **UI:** Called on app load to store CSRF for subsequent auth form posts.

---

## 3) Dashboard & Analytics

> **Note:** The current OpenAPI has *ingestion* telemetry endpoints only. The *UI* for analytics is specified here; data retrieval will come from the internal analytics/timeseries service (out of this spec). We still provide deep links to related entities and use Observations/Plantings/Plans data available via CRUD endpoints.

### 3.1 Overview (KPIs)

* **Cards:**

  * Active greenhouses, zones w/ active plantings, devices online (from `controllers.last_seen` freshness heuristic), open alerts (fallback active, plan stale).
  * Today’s irrigation tasks (from Plan payload preview), most recent observations, upcoming harvest windows (from `crops.growing_days` + planting start).
* **Actions:** “Go to Greenhouse”, “New Observation”, “Start Planting”.

### 3.2 Analytics (History)

* **Charts:**

  * Environment trends (Temp/VPD/CO₂/Light) vs plan setpoints.
  * Observation trends (height cm, health score).
  * Actuation runtime summaries (fan/heater/vent).
* **Filters:** greenhouse, zone, date range, variables.
* **Note:** The UI contract expects an internal `/analytics/...` read API (not defined here) and gracefully degrades to “No data yet” until available.

### 3.3 System Health

* **Endpoints:**

  * `GET /health` → show service status.
  * `GET /meta/sensor-kinds`, `GET /meta/actuator-kinds` → populate reference cards.
* **Usage:** Quick admin diagnostic page.

---

## 4) Greenhouses (API tag: **CRUD**)

### 4.1 List / Create

* **Endpoints:**

  * `GET /greenhouses?page=&page_size=`
  * `POST /greenhouses`
* **Create Form Fields:** `title*`, `description`, `is_active`, `latitude`, `longitude`, rails/bounds (`min/max temp_c`, `min/max vpd_kpa`, enthalpy thresholds, `site_pressure_hpa`), `context_text` (planner notes).
* **Validations:** Per schema ranges (lat/long, numbers, string lengths).
* **Errors:** `409` title uniqueness (if enforced), `400` bad field.

### 4.2 Detail (Summary & Context)

* **Endpoint:** `GET /greenhouses/{id}`
* **Panels:**

  * **Summary:** ID, rails, bounds, location; edit via `PATCH /greenhouses/{id}`.
  * **Context Text:** rich textarea (save via patch).
  * **Counts:** zones, controllers, sensors, actuators, active plan version.

---

## 5) Zones (API tag: **CRUD**)

### 5.1 List / Create (within a greenhouse)

* **Endpoints:**

  * `GET /zones?greenhouse_id=&is_active=&sort=&page=&page_size=`
  * `POST /zones`
* **Create Fields:** `greenhouse_id*`, `zone_number* (≥1)`, `location ∈ {N,NE,...}`, `context_text`.
* **Sort:** `zone_number` default.

### 5.2 Zone Detail

* **Endpoint:** `GET /zones/{id}`
* **Panels:**

  1. **Context for Planner** (edit via `PATCH /zones/{id}`).
  2. **Active Planting** (see §10).
  3. **Observations** (latest 10 with link to full list §11).
  4. **Linked Sensors/Actuators** (from mappings/assignments).
* **Actions:** Edit zone (`PATCH`), Delete zone (`DELETE /zones/{id}`; confirm + cascade safety note).

---

## 6) Controllers & Onboarding (API tags: **CRUD**, **Onboarding**, **Authentication**)

### 6.1 Controllers — List / Create

* **Endpoints:**

  * `GET /controllers?greenhouse_id=&is_climate_controller=&sort=&page=&page_size=`
  * `POST /controllers`
* **Create Fields:** `greenhouse_id*`, `device_name* (^verdify-[0-9a-f]{6}$)`, `label`, `model`, `is_climate_controller`, `fw_version`, `hw_version`.
* **Notes:** Devices typically appear via claim; manual create is admin‑only.

### 6.2 Controller Detail

* **Endpoints:**

  * `GET /controllers/{controller_id}`
  * `PATCH /controllers/{controller_id}` (label/model/is\_climate\_controller/fw/hw)
  * `DELETE /controllers/{controller_id}` (revokes device\_token)
* **Panels:**

  * **Identity:** device\_name, last\_seen, firmware/hardware.
  * **Security:**

    * Rotate token → `POST /controllers/{controller_id}/rotate-token` (shows new token & expiry).
    * Revoke token → `POST /controllers/{controller_id}/revoke-token`.
  * **Sensors/Actuators**, **Fan Groups**, **Buttons** (sections link to respective screens filtered by `controller_id`).
  * **Device Debug (lab):**

    * **Paste X‑Device‑Token** to call:

      * `GET /controllers/me/config`
      * `GET /controllers/me/plan`
    * **Fetch by name (requires token + device\_name):**

      * `GET /controllers/by-name/{device_name}/config`
    * **Fetch plan by controller id (requires token):**

      * `GET /controllers/{controller_id}/plan`
    * Displays ETag/Last-Modified headers when present.

### 6.3 Device Onboarding — Claim Wizard

* **User Flow (operator):**

  1. Power the controller; it calls `/hello` (informational; app does not call).
  2. In app, open **Claim Controller**.
  3. Enter `device_name` + `claim_code` + target `greenhouse_id`.
  4. Submit → `POST /controllers/claim` → shows returned controller and issued device\_token (with expiry).
* **Errors:**

  * `404` (unknown device\_name/claim\_code); `409` (already claimed).
* **Post‑claim:** The *controller* later calls `/controllers/{controller_id}/token-exchange` (documented in onboarding help panel; not invoked by app).

---

## 7) Sensors (API tag: **CRUD**) & Zone Mapping

### 7.1 Sensors — List / Create / Edit

* **Endpoints:**

  * `GET /sensors?kind=&controller_id=&greenhouse_id=&sort=&page=&page_size=`
  * `POST /sensors`
  * `GET /sensors/{id}`
  * `PATCH /sensors/{id}`
* **Create/Edit Fields:** controller\*, name\*, `kind` (dropdown from `/meta/sensor-kinds`), `scope ∈ {zone, greenhouse, external}`, include\_in\_climate\_loop, Modbus fields, value transform (scale/offset), poll\_interval\_s.
* **Validations:** Enumerations, numeric ranges, optional ints.

### 7.2 Map Sensors to Zones

* **Endpoints:**

  * Create mapping: `POST /sensor-zone-maps` (sensor\_id\*, zone\_id\*, kind\*)
  * Delete mapping: `DELETE /sensor-zone-maps?sensor_id=&zone_id=&kind=`
* **UI:** On Zone Detail → “Map Sensor” (search sensors filtered by compatible `kind`); list mappings with remove action.
* **Notes:** Multi‑zone supported per API.

---

## 8) Actuators & Fan Groups (API tag: **CRUD**)

### 8.1 Actuators — List / Create / Edit / Delete

* **Endpoints:**

  * `GET /actuators?controller_id=`
  * `POST /actuators`
  * `GET /actuators/{id}`
  * `PATCH /actuators/{id}`
  * `DELETE /actuators/{id}`
* **Fields:** controller\*, name\*, kind (from `/meta/actuator-kinds`), relay\_channel, min\_on\_ms/min\_off\_ms, fail\_safe\_state (`on|off`), optional zone assignment.
* **UI:** Table with controller, kind, zone; detail form; delete with confirm.

### 8.2 Fan Groups — List / Create / Manage Members

* **Endpoints:**

  * `GET /fan-groups?controller_id=`
  * `POST /fan-groups`
  * `GET /fan-groups/{id}`
  * Add member: `POST /fan-groups/{id}/members` (actuator\_id\*)
  * Remove member: `DELETE /fan-groups/{id}/members?actuator_id=`
  * `DELETE /fan-groups/{id}`
* **UI:**

  * Fan Group detail shows current actuator members; add via searchable picker of compatible actuators (kind=fan).
  * Removing a member requires confirmation.

---

## 9) Buttons (Manual Override) (API tag: **CRUD**)

### 9.1 Buttons — List / Create / Edit / Delete

* **Endpoints:**

  * `GET /buttons?controller_id=`
  * `POST /buttons`
  * `GET /buttons/{id}`
  * `PATCH /buttons/{id}`
  * `DELETE /buttons/{id}`
* **Fields:** controller\*, `button_kind ∈ {cool,heat,humid}`, optional `target_temp_stage` / `target_humi_stage` (−3..+3), `timeout_s ≥ 1`.
* **UX:** Educate that pressing a physical button latches an override for `timeout_s`.

---

## 10) State Machine Grid & Fallback (API tag: **CRUD**)

### 10.1 Grid (49 cells)

* **Endpoints:**

  * `GET /state-machine-rows?greenhouse_id=`
  * Create row: `POST /state-machine-rows`
  * Get row: `GET /state-machine-rows/{id}`
  * Update row: `PUT /state-machine-rows/{id}`
  * Delete row: `DELETE /state-machine-rows/{id}`
* **UI Model:** 7×7 matrix for `temp_stage` (rows −3..+3) × `humi_stage` (cols −3..+3). Each cell opens an editor:

  * must\_on\_actuators \[IDs], must\_off\_actuators \[IDs], must\_on\_fan\_groups \[{fan\_group\_id,on\_count}].
* **Validations:** Stage ranges, fan\_group on\_count ≥ 0 (create) or ≥ 1 (update model’s stricter rule).
* **Conflict Handling:** `409` if duplicate stage pair exists.

### 10.2 Fallback

* **Endpoint:** `PUT /state-machine-fallback/{id}` where `{id}` is greenhouse id.
* **Fields:** arrays of must\_on/off actuators and must\_on\_fan\_groups.
* **UX:** Dedicated “Fallback” panel with simple pickers.

---

## 11) Crops, Plantings & Observations (API tag: **CRUD**)

*(Consolidates and supersedes prior addendum; aligned to hyphenated paths)*

### 11.1 Crop Catalog

* **Endpoints:**

  * `GET /crops?page=&page_size=`
  * `POST /crops`
  * `GET /crops/{id}`
  * `PATCH /crops/{id}`
  * `DELETE /crops/{id}`
* **List:** search (client‑side), sort (name, updated\_at—client), pagination (50 default).
* **Editor Fields:** name\*, description, expected\_yield\_per\_sqm, growing\_days, recipe (staged JSON with guided editor).
* **Recipe UX:** stage cards with day ranges and targets (temp, VPD, photoperiod, irrigation hints, soil VWC if used). Form validates monotonic non‑overlapping ranges; `min ≤ max`.
* **Advanced:** JSON editor toggle writes to `crop.recipe`.

### 11.2 Plantings (Zone Crops)

* **Endpoints:**

  * `GET /zone-crops?zone_id=&crop_id=&is_active=&sort=&page=&page_size=`
  * `POST /zone-crops`
  * `GET /zone-crops/{id}`
  * `PATCH /zone-crops/{id}`
* **Start Planting Wizard:**

  * Step 1: Select Crop.
  * Step 2: Start Date (default today UTC), Area (m², optional), Notes (captured in observation later).
  * Submit → `POST /zone-crops { zone_id, crop_id, start_date, area_sqm? }`.
  * `409` if zone already has an active planting ⇒ inline resolution link to end existing planting.
* **Planting Detail:**

  * Shows **Day N of M** using crop.growing\_days + start\_date.
  * **Current Stage** inferred from recipe (if any).
  * Actions: **End Planting** (`PATCH /zone-crops/{id}` with `end_date`, `is_active=false`, optional `final_yield ≥ 0`).
  * Recent Observations table with “Add Observation”.

### 11.3 Observations

* **Endpoints:**

  * List: `GET /observations?zone_crop_id=&zone_id=&observation_type=&sort=&page=&page_size=`

    * *Note:* API `sort` uses `observation_date`; UI maps it to `observed_at`.
  * Create: `POST /observations`
  * Update: `PATCH /observations/{id}`
  * Delete: `DELETE /observations/{id}`
  * Upload URL (optional flow): `POST /observations/{id}/upload-url`
* **Create/Edit Fields:** `observed_at* (ISO UTC)`, `height_cm` (≥0, optional), `health_score` (1..10 or null), `notes` (≤2000), `image_url` (optional).
* **Image Upload Flows:**

  * **Two‑step (preferred):** `POST /observations` (create with metadata but no image), then `POST /observations/{id}/upload-url` → PUT to presigned URL → PATCH observation with `image_url` if required by backend, or backend may attach automatically.
  * **Direct URL:** paste a public URL in create/edit.
* **List Filters:** date range (client), health range (client), has photo (client).
* **Detail:** photo preview, metrics, notes; actions to edit/delete (confirm).

---

## 12) Plans (API tag: **Plan**)

### 12.1 Plan Versions

* **Endpoints:**

  * `GET /plans?greenhouse_id=&active=&sort=&page=&page_size=`
  * `POST /plans`
* **List:** Show version, `effective_from/to`, `is_active`, created\_at; drill‑down viewer shows the full payload schedule—setpoints (30‑min entries), irrigation/fertilization/lighting tasks.
* **Create:** JSON editor with schema hints; validate `effective_from < effective_to`; ensure only one active plan (API enforces; on `409` show guidance).

### 12.2 Device‑side Plan Viewers (lab)

* Covered in **Controller Detail → Device Debug** using device token to call `/controllers/me/plan` or `/controllers/{controller_id}/plan`.

---

## 13) Config — Publish & Diff (API tag: **Config**)

### 13.1 Publish

* **Endpoint:** `POST /greenhouses/{id}/config/publish`
* **UI:**

  * “Publish” button (default **dry run = false**).
  * “Preview Dry Run” checkbox → `dry_run=true` to fetch a generated result without persisting.
  * Show returned `version`, warnings/errors, and payload viewer + downloadable JSON.
* **ETag semantics:** Controllers will fetch via device endpoints; app displays the generated version to admins.

### 13.2 Diff

* **Endpoint:** `GET /greenhouses/{id}/config/diff`
* **UI:** Patch‑like view with **added/removed/changed** arrays. Buttons: “Publish now” (links to §13.1).

### 13.3 Device Config Viewers (lab)

* Covered in **Controller Detail → Device Debug** using `/controllers/me/config` and `/controllers/by-name/{device_name}/config`.

---

## 14) Meta & Health (API tag: **Meta**)

* **Health:** `GET /health` → status badge on Dashboard > System Health.
* **Sensor Kinds:** `GET /meta/sensor-kinds` → populate sensor kind dropdowns and reference labels/tooltips.
* **Actuator Kinds:** `GET /meta/actuator-kinds` → populate actuator kind dropdowns and tooltips.

---

## 15) Developer Tools (Lab‑only; behind feature flag)

### 15.1 Telemetry Uploader

* **Endpoints:**

  * `POST /telemetry/sensors`
  * `POST /telemetry/actuators`
  * `POST /telemetry/status`
  * `POST /telemetry/inputs`
  * `POST /telemetry/batch` (supports `Content-Encoding: gzip`)
* **UI:** Forms to craft frames and post with optional `Idempotency-Key`. Display rate‑limit headers and accepted/rejected counts.
* **Headers:** Must include **X‑Device‑Token** (DeviceToken scheme).
* **Purpose:** Developer validation and demo; not needed for growers.

---

## 16) Screen Blueprints (key wireframes)

> (ASCII wireframes are indicative; final UI uses responsive cards/tables)

### 16.1 Dashboard — Overview

```
[ Dashboard ]
KPIs: [Active GH: 2] [Active Zones: 8] [Devices Online: 5/6] [Alerts: 2]
Plan Window: [Today 06:00–18:00]  Setpoint Bands: Temp 20–26 °C, VPD 0.6–1.2 kPa
Quick Actions: [New Observation] [Start Planting] [Claim Controller]
Recent Observations (5)   Upcoming Tasks (Plan)
```

### 16.2 Greenhouse Detail — Tabs

```
[ Greenhouse A ]  (rails & bounds summary)   [ Edit ]
Tabs: Summary | Zones | Controllers | State Machine | Config | Plans

Summary:
 Context for Planner [ textarea ........ ]  [Save]

Zones:
 | # | Location | Active Planting | Last Obs | Actions |
 | 1 | NE       | Tomato (Day 11) | 2025‑08‑11  | [Detail]

Controllers:
 | Device Name       | Label | Climate | Last Seen      | Actions |
 | verdify-a1b2c3    | Main  |  Yes    | 2025‑08‑13 18:05Z | [Detail]
```

### 16.3 Zone Detail — Planting & Observations

```
Zone #1 (NE)
Context [editable]

Active Planting
  Crop: Tomato | Started: 2025‑08‑01 | Area: 4.0 m²
  [ View Planting ] [ End Planting ]   [ Start Planting ] (disabled when active)

Observations (recent)
  | Observed At (UTC)      | Height cm | Health | Photo | Notes |
  | 2025‑08‑11T17:00:00Z   | 8.0       | 7      | [🖼]  | tip burn...
  [ View All ] [ Add Observation ]
```

### 16.4 State Machine Grid

```
Temp\VPD  -3  -2  -1   0  +1  +2  +3
 -3       [Edit]...[Edit]
 ...
 +3       [Edit]...[Edit]

[Fallback Config]  must_on: [ ]  must_off: [ ]  fan_groups: [{id,on_count}]
```

---

## 17) Validation & Error Mapping

Centralized mapping of API error codes to UI feedback:

| API                      | Typical Cause                                   | UI Handling                                                    |
| ------------------------ | ----------------------------------------------- | -------------------------------------------------------------- |
| `E401_UNAUTHORIZED`      | Missing/invalid bearer or device token          | Redirect to login (UserJWT) or show token input (Device Debug) |
| `E403_FORBIDDEN`         | Insufficient permissions                        | Banner “You don’t have access to do this.”                     |
| `E404_NOT_FOUND`         | Wrong ID/filter                                 | Toast + redirect back to list                                  |
| `E409_CONFLICT`          | Unique/staging conflict, active planting exists | Inline callout with actionable link (e.g., end planting)       |
| `E422_UNPROCESSABLE`     | Validation failed                               | Per‑field inline errors, keep user input                       |
| `E429_TOO_MANY_REQUESTS` | Rate limit                                      | Show Retry‑After seconds; auto‑retry option in dev tools       |

Field‑level validations mirror schema constraints (patterns, enums, numeric ranges, string lengths). Date/time pickers ensure UTC serialization.

---

## 18) Accessibility, i18n, performance

* **A11y:** Labels, ARIA roles, focus order, keyboard navigation, contrast ≥ 4.5:1, semantic tables.
* **i18n:** Copy strings centralized; units fixed metric; number/date localization on display.
* **Perf:** Use pagination everywhere; debounce search; cache reference lists (sensor/actuator kinds).

---

## 19) Security model

* **UserJWT** (bearer) for all app/admin calls.
* **DeviceToken** via `X‑Device‑Token` header only in **lab debug** and **telemetry uploader**.
* **CSRF** fetched for browser‑based auth forms.
* **PII:** Only user email; store tokens in memory (not localStorage) if using web to mitigate XSS; rotate controller tokens from admin UI when needed.

---

## 20) Testing & Acceptance (E2E)

1. **Auth:** Register → login → logout; invalid login rejected.
2. **Greenhouse CRUD:** Create GH, edit rails/context, delete (if empty).
3. **Zones:** Create zone; edit context; delete.
4. **Controllers:** Claim device; view detail; rotate and revoke token; delete controller.
5. **Sensors:** Create sensor; edit fields; map to zone; unmap.
6. **Actuators:** Create actuator; assign to zone; edit min\_on/off; delete.
7. **Fan Groups:** Create; add/remove members; delete group.
8. **Buttons:** Create heat button with timeout; update; delete.
9. **State Machine:** Add row for (0,0); update; delete; configure fallback.
10. **Crops:** Create with staged recipe; patch; delete.
11. **Plantings:** Start planting in empty zone; blocked when one is active; end planting with final\_yield.
12. **Observations:** Add with photo (upload‑URL flow), edit, delete; list filters.
13. **Plans:** Create plan version; list; ensure at most one active (409 on conflict).
14. **Config:** Diff shows changes; publish (dry run + real); snapshot version appears.
15. **Meta & Health:** Health returns “healthy”; sensor/actuator kinds populate pickers.
16. **Device Debug:** Paste token; fetch `/controllers/me/config` & `/me/plan`; view ETags.
17. **Telemetry Uploader:** Post batch; see `accepted` vs `rejected` & rate‑limit headers.

---

## 21) Endpoint → Screen Coverage Map

> Every path in OpenAPI has a corresponding page, panel, or tool in the app.

| API Path                                             | Screen / Panel                                    |
| ---------------------------------------------------- | ------------------------------------------------- |
| **/auth/register (POST)**                            | Auth → Register                                   |
| **/auth/login (POST)**                               | Auth → Login                                      |
| **/auth/csrf (GET)**                                 | Auth bootstrap (hidden)                           |
| **/auth/revoke-token (POST)**                        | Auth → Logout                                     |
| **/controllers/{id}/revoke-token (POST)**            | Controller Detail → Security                      |
| **/controllers/{id}/rotate-token (POST)**            | Controller Detail → Security                      |
| **/hello (POST)**                                    | Onboarding help (informational; device‑initiated) |
| **/controllers/claim (POST)**                        | Onboarding → Claim Controller                     |
| **/controllers/{id}/token-exchange (POST)**          | Onboarding help (informational; device‑initiated) |
| **/controllers/by-name/{device\_name}/config (GET)** | Controller Detail → Device Debug (Paste token)    |
| **/controllers/{id}/plan (GET)**                     | Controller Detail → Device Debug (Paste token)    |
| **/controllers/me/config (GET)**                     | Controller Detail → Device Debug (Paste token)    |
| **/controllers/me/plan (GET)**                       | Controller Detail → Device Debug (Paste token)    |
| **/greenhouses/{id}/config/publish (POST)**          | Greenhouse → Config Publish                       |
| **/greenhouses/{id}/config/diff (GET)**              | Greenhouse → Config Diff                          |
| **/telemetry/sensors (POST)**                        | Developer Tools → Telemetry Uploader              |
| **/telemetry/actuators (POST)**                      | Developer Tools → Telemetry Uploader              |
| **/telemetry/status (POST)**                         | Developer Tools → Telemetry Uploader              |
| **/telemetry/inputs (POST)**                         | Developer Tools → Telemetry Uploader              |
| **/telemetry/batch (POST)**                          | Developer Tools → Telemetry Uploader              |
| **/greenhouses (GET/POST)**                          | Greenhouses → List/Create                         |
| **/greenhouses/{id} (GET/PATCH/DELETE)**             | Greenhouse → Detail/Edit/Delete                   |
| **/zones (GET/POST)**                                | Zones (tab) → List/Create                         |
| **/zones/{id} (GET/PATCH/DELETE)**                   | Zone Detail → Summary/Edit/Delete                 |
| **/crops (GET/POST)**                                | Crops → Catalog/List/Create                       |
| **/crops/{id} (GET/PATCH/DELETE)**                   | Crops → Editor/View/Delete                        |
| **/zone-crops (GET/POST)**                           | Plantings → List (filter) / Start Planting        |
| **/zone-crops/{id} (GET/PATCH)**                     | Planting Detail → View/End/Update                 |
| **/observations (GET/POST)**                         | Observations → List/Create                        |
| **/observations/{id} (PATCH/DELETE)**                | Observation Detail → Edit/Delete                  |
| **/observations/{id}/upload-url (POST)**             | Observation Detail → Upload image                 |
| **/controllers (GET/POST)**                          | Controllers → List/Create                         |
| **/controllers/{id} (GET/PATCH/DELETE)**             | Controller Detail → View/Edit/Delete              |
| **/sensors (GET/POST)**                              | Sensors → List/Create                             |
| **/sensors/{id} (GET/PATCH)**                        | Sensor Detail → View/Edit                         |
| **/sensor-zone-maps (POST/DELETE)**                  | Zone Detail → Map/Unmap Sensors                   |
| **/actuators (GET/POST)**                            | Actuators → List/Create                           |
| **/actuators/{id} (GET/PATCH/DELETE)**               | Actuator Detail → View/Edit/Delete                |
| **/fan-groups (GET/POST)**                           | Fan Groups → List/Create                          |
| **/fan-groups/{id}/members (POST/DELETE)**           | Fan Group Detail → Manage Members                 |
| **/fan-groups/{id} (GET/DELETE)**                    | Fan Group Detail → View/Delete                    |
| **/buttons (GET/POST)**                              | Buttons → List/Create                             |
| **/buttons/{id} (GET/PATCH/DELETE)**                 | Button Detail → View/Edit/Delete                  |
| **/state-machine-rows (GET/POST)**                   | State Machine Grid → List/Add Row                 |
| **/state-machine-rows/{id} (GET/PUT/DELETE)**        | State Machine Row Editor → View/Update/Delete     |
| **/state-machine-fallback/{id} (PUT)**               | State Machine Grid → Fallback Panel               |
| **/plans (GET/POST)**                                | Plans → List/Create                               |
| **/health (GET)**                                    | Dashboard → System Health                         |
| **/meta/sensor-kinds (GET)**                         | Diagnostics + Sensor forms                        |
| **/meta/actuator-kinds (GET)**                       | Diagnostics + Actuator forms                      |

---

## 22) Data models (UI ↔ API payload excerpts)

> These examples guide client payload shaping (non‑exhaustive). All timestamps serialized as ISO UTC.

### 22.1 Create Zone

```json
POST /zones
{
  "greenhouse_id": "uuid-gh",
  "zone_number": 1,
  "location": "NE",
  "context_text": "Shadier bed near service door."
}
```

### 22.2 Start Planting

```json
POST /zone-crops
{
  "zone_id": "uuid-zone",
  "crop_id": "uuid-crop",
  "start_date": "2025-08-12T00:00:00Z",
  "area_sqm": 4.0
}
```

### 22.3 Add Observation (direct URL flow)

```json
POST /observations
{
  "zone_crop_id": "uuid-zonecrop",
  "observed_at": "2025-08-12T18:00:00Z",
  "height_cm": 12.3,
  "health_score": 7,
  "image_url": "https://cdn.example/obs/abc.jpg",
  "notes": "Leaves perked up after watering."
}
```

### 22.4 Publish Config (dry run)

```json
POST /greenhouses/{id}/config/publish
{ "dry_run": true }
```

### 22.5 Create Plan (minimal)

```json
POST /plans
{
  "greenhouse_id": "uuid-gh",
  "is_active": true,
  "effective_from": "2025-09-01T00:00:00Z",
  "effective_to": "2025-10-01T00:00:00Z",
  "payload": {
    "version": 1,
    "greenhouse_id": "uuid-gh",
    "effective_from": "2025-09-01T00:00:00Z",
    "effective_to": "2025-10-01T00:00:00Z",
    "setpoints": [
      {
        "ts_utc": "2025-09-01T00:00:00Z",
        "min_temp_c": 20,
        "max_temp_c": 26,
        "min_vpd_kpa": 0.6,
        "max_vpd_kpa": 1.2
      }
    ]
  }
}
```

---

## 23) Open questions & API/UX notes (tracked)

* **Analytics reads:** Current OpenAPI exposes ingest only. UI defines analytics surfaces; reads will attach to a separate internal service (TBD).
* **Observation list sort key:** API uses `observation_date` in `sort` values while schema field is `observed_at`; client treats them as aliases.
* **Plan editing UX:** Plan JSON editor is advanced; guided composer (time blocks) is a phase‑2 enhancement.

---

## 24) Implementation Guide (for devs)

* **Tech (suggested):** React/TypeScript + Router; tables with server‑side pagination; form library with Zod/JSON‑schema validators generated from OpenAPI; API client from OpenAPI generator; toast + inline error components; auth context for Bearer; feature flagging for Dev Tools.
* **Caching:** SWR/RTK Query with ETag/Last‑Modified awareness where available.
* **Testing:** Cypress E2E aligned with §20; component tests for forms; contract tests to ensure payload shapes and enum adherence.

---

## 25) Done‑ness checklist

* [x] Every endpoint has a corresponding screen/panel/tool (see §21).
* [x] CRUD coverage for greenhouses, zones, controllers, sensors, actuators, fan groups, buttons, state machine rows/fallback.
* [x] Crop catalog, plantings, observations fully specified and aligned to hyphenated paths.
* [x] Config publish/diff flows specified; plan versioning UIs defined.
* [x] Onboarding (claim) covered; device token debugging tools provided.
* [x] Dashboard & analytics surfaces designed (backed by future read service).
* [x] Validation & error mapping reflect OpenAPI constraints and error codes.
* [x] Security model (UserJWT vs DeviceToken) documented.
* [x] Accessibility and performance guidance included.

---

**End of APP.md**
