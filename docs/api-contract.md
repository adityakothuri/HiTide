# HiTide API contract (backend ⇄ frontend)

> This contract covers the legacy driver-rescue REST/WebSocket workflow.
> The new `/api/evidence/*` endpoints, operations polling, request examples, and
> persistence requirements are documented in [the evidence milestone record, section 10](history/2026-11-07-evidence-milestone.md#10-api-inventory).
> The evidence and legacy simulation state are separate; the existing WebSocket
> snapshot is not the evidence state endpoint.

Source of truth: `backend/api/schemas.py` (Pydantic). Interactive docs: http://localhost:8000/docs once the backend is running.

Base URL: `http://localhost:8000`. CORS is open for `localhost:5173` (Vite).

### Statewide monitoring

`GET /api/feeds/recent` defaults to `scope=texas&max_age_minutes=30`. Supported ages are integers from 15 through 30. Use `scope=kerrville` for the local test query. The result includes `scope`, UTC `as_of`, `max_age_minutes` and `sources`. Each source includes `records` (raw intake envelopes), `excluded` (counts by reason) and `status` (complete, partial, unavailable). Construction context uses source drivetexas_work_zones, with publication time in provider_metadata.feed_updated_at and original WZDx LineString features. The Texas observation sources are `nws_alerts`, `usgs_gage` and `nws_local_storm_reports`. An empty live result is a completed request. Unreported road conditions remain unknown. [Source mappings and freshness rules](MAP_DATA_ACCESS.md)

> **To see live data:** start the backend (`cd backend && uv run uvicorn app.main:app --reload`), connect to `/ws`, then `curl -X POST localhost:8000/api/demo/start`. The flood starts rising and `segments.update` events stream in (sim runs 60x real time).
>
> **Status (2026-11-07):** live now: `/api/health`, `/api/town`, `/api/state`, `/api/feeds`, `/api/demo/start|reset`, WS `snapshot`/`alert`/`segments.update`. The other endpoints and events are coming in Phases 2–5 with exactly these shapes.

## REST

| Method | Path | Returns |
|---|---|---|
| GET | `/api/town` | `{segments: FeatureCollection, river: Feature, bounds: [w,s,e,n], center: [lat,lon]}`. Static. Fetch once and cache. Each segment feature has `properties.edge_id`, `name`, `length_m`, `elev_m`. |
| GET | `/api/state` | `StateSnapshot`: same as the first WS message |
| GET | `/api/feeds` | `{nws: {...}, usgs_gage: {...}, flood_impacts: {...}}`. Each has `source: live|cached|unavailable`. |
| GET | `/api/cases` | `Case[]`, sorted by urgency (descending) |
| POST | `/api/cases/{id}/reply` | body `{"reply": "safe" \| "need_help"}`. Driver view buttons. |
| POST | `/api/demo/start` | Starts the scripted 7-step demo (compressed timers). |
| POST | `/api/demo/reset` | Resets the sim to t=0. |
| GET | `/api/drivers/{id}` | Driver view data: `{driver, pretrip_warning?, active_turn_around?, case?}` |
| GET | `/static/drone/<file>` | Drone sample images (raw + annotated) |
| GET | `/api/health` | `{ok, segments, drivers, ws_clients, modes: {data_mode: test\|real\|manual, outreach: mock\|stable\|photon2, feeds: cache\|live, region: replay\|live, db}}`; the UI badge reads `modes` |

**Segment ids:** segments are *directed* edges, so a two-way street appears twice (`u-v-0` and `v-u-0`) with the same geometry. Draw both or dedupe by geometry. Colour each one by its status from the latest `segments.update`. Any id that isn't listed is `open`.

## Privacy and security behaviour (2026-11-07)

- **Before a warning is active**, the snapshot has `drivers: []` and `drivers_opted_in: 100`, and no `drivers.update` events are sent. Locations appear once the `alert` arrives (opt-in terms).
- `urgency_reasons` use coarse bands ("older driver (65+)", "low-clearance vehicle"), never exact age or model.
- Drivers in `data/drivers.json` carry a simulated `profile` block (see `docs/driver-profile.md`). It is backend-only and is **not** part of any payload above. Any future field that exposes it to the frontend gets added here first.
- `/ws` and the POST endpoints reject browser origins other than `localhost`/`127.0.0.1` (any port). If you serve the UI from elsewhere, set `FRONTEND_ORIGIN_REGEX` on the backend.

## WebSocket `ws://localhost:8000/ws`

Every message has this envelope:

```json
{"type": "segments.update", "seq": 42, "ts": "2026-11-07T23:10:00Z", "payload": { ... }}
```

| type | payload | UI use |
|---|---|---|
| `snapshot` | `StateSnapshot` | Sent first on connect. Replace all state with it. |
| `segments.update` | `{t_sim_s, river_wse_m, segments:[{edge_id, depth_in, status}]}` | Diff (changed segments only). Recolour roads. |
| `drivers.update` | `{drivers:[{id,name,lat,lon,heading_deg,situation,is_demo,urgency}]}` | Move markers. `situation`: parked, planning, driving, stopped_in_water. `urgency` (0..1) is the case urgency for a driver with an open case, otherwise the latest pre-trip or turn-around score (includes the simulated profile), else 0. Shape unchanged. |
| `alert` | `{id,event,headline,active,simulated,polygon}` | NWS banner + driver "HiTide active" status |
| `outreach` | `{id,ts,driver_id,recipient,channel,body,mode,status,case_id,provider?,call_id?}` | Case timeline + driver phone mock. `mode: mock` means it was not really sent; live sends report `mode: photon`. `provider` (`stable` or `photon2`) is present only on live sends. `call_id` (ElevenLabs conversation id) is present only on placed voice calls. Both are optional and additive. |
| `turn_around` | `{driver_id,message,hazard_edge_id,hazard_depth_in,distance_m}` | **Driver view: full-screen red alert + `speechSynthesis.speak(message)`** |
| `reroute` | `{driver_id,reason,route:GeoJSON LineString,blocked_edge_ids,distance_m}` | Draw the new route (green), mark blocked segments |
| `case.update` | `Case` (full object, see below) | Upsert into the case queue, then sort by `urgency` |
| `drone.update` | `{id,case_id,lat,lon,eta_s,status}` | Animate the drone icon + ETA |
| `counters` | `{drivers_warned,drivers_rerouted,cars_stopped_in_water,people_verified,est_claims_avoided_usd}` | Header counters |
| `demo.step` | `{step,title,detail}` | Optional narration caption |

### Road status colours (suggested)

| status | depth | meaning |
|---|---|---|
| `open` | < 3 in | normal |
| `caution` | 3–6 in | yellow |
| `closed` | ≥ 6 in | orange-red, closed to cars |
| `float` | ≥ 12 in | red, vehicles may float |
| `boat` | ≥ 24 in | dark red / purple, boat only |

### Case object

```json
{
  "id": "case-001", "driver_id": "d-087", "driver_name": "Margaret H.",
  "state": "drone_en_route",
  "urgency": 0.91, "urgency_reasons": ["stopped in 20 in of water", "night", "age 78", "water rising"],
  "responder_flag": true,
  "location": {"lat": 30.043, "lon": -99.131}, "depth_in": 20.4,
  "opened_at": "2026-11-07T23:41:00Z",
  "timeline": [
    {"ts": "...", "t_case_s": 0, "kind": "state", "text": "Car stopped in floodwater on Water St"},
    {"ts": "...", "t_case_s": 0, "kind": "outreach", "text": "Voice call to driver (mock): no answer"},
    {"ts": "...", "t_case_s": 0, "kind": "flag", "text": "High risk: flagged to responders"}
  ],
  "vision": null,
  "responder_view": {"location": {"lat": 30.043, "lon": -99.131}, "people_count": null, "water_depth_in": 20.4}
}
```

Case states, in order: `monitoring → calling → contacting_family → drone_en_route → verified → handed_to_responders → resolved`. A reply from the driver or a family member jumps the case to `resolved` (safe) or keeps it escalated (need help).

When the drone arrives, `vision` is filled in:

```json
{"image_url": "/static/drone/flood_03.jpg", "annotated_url": "/static/drone/flood_03_annotated.jpg",
 "car_detected": true, "water_level": "windows", "water_level_source": "manual_label",
 "people": [{"placement": "on_roof", "box": [412, 120, 470, 230], "conf": 0.81}],
 "night_mode": true, "thermal_simulated": true, "recommendation": "boat_required"}
```

At night (`night_mode: true`), `image_url` points to a **simulated thermal** frame (`*_thermal.jpg`, stamped "SIMULATED THERMAL"). `annotated_url` always shows the real detections on the daylight sample image.

The UI must label simulated parts: `thermal_simulated`, `alert.simulated`, `outreach.mode == "mock"`, and `water_level_source == "manual_label"`.

**Privacy:** the responder panel shows only `responder_view` (location, people count, water depth). Age and vehicle appear only inside `urgency_reasons` on the State Farm ops case card.

## Outreach provider note

`PHOTON_MODE` selects the sender: `mock` (default), `stable` (Photon Spectrum sidecar) or `photon2` (Photon 2.0 API). All live sends keep `outreach.mode == "photon"`; use the optional `provider` field to tell them apart. Frontends should treat `provider` and `call_id` as optional and ignore them if absent.

## Proposed additions (frontend)

> Added 2026-11-07 by the frontend. All of these are **optional**. The UI works without them and falls back as noted. Shapes are mirrored in `frontend/src/data/types.ts` (marked `proposed`).

| Where | Field / endpoint | Why | Frontend fallback until it exists |
|---|---|---|---|
| `DroneState` | `crew_eta_s: float` | Ground crew ETA, so the console can show **minutes gained** = crew ETA − drone ETA | Offline demo uses an estimated 17 min crew ETA. Live mode shows "Crew ETA not available". |
| `Case` | `vehicle: str` (e.g. "2019 Toyota Camry") | Case header on the State Farm ops card (not the responder card) | Demo persona table in `frontend/src/data/personas.ts` |
| `Case` | `emergency_contact_name: str` | Driver app says "We contacted Maria" | Persona table, then "your emergency contact" |
| `TimelineEntry` | `simulated: bool` | Label simulated or mock rows without parsing "(mock" out of `text` | The UI also looks for "(mock" or "(simulated" in the text |
| `TimelineEntry` (outreach) | `status: sent\|delivered\|read\|replied`, `reply: str?` | Show read and reply state in the case timeline | Shows the text as sent |
| REST | `POST /api/drones/{id}/command` body `{"command": "return"}` → emits `case.update` + `drone.update` | Recall a drone from the console. Drones only map and report cars in the water to emergency services; `speak` and `drop_jacket` were removed 2026-11-08 (422) | **Implemented 2026-11-08.** 404 if the drone has no open case; the UI then adds a local row labelled simulated |
| `StateSnapshot` | `reroutes: Reroute[]`, `turn_arounds: TurnAround[]` | A driver view that reconnects mid-trip can restore its route and alert | Lost on reconnect |

The **feed status** keys returned by `GET /api/feeds` are `nws_alerts`, `usgs_gage`, `usgs_flood_impacts` (each with `source` and `fetched_at`), not `nws` / `flood_impacts` as written in the REST table above. The frontend reads the actual keys.

## Hill Country scenario: critical points and drone tours (2026-11-08)

A second, separate demo replays the **real July 4, 2025 flood** over Hunt → Ingram → Kerrville (overview.md §8, math in `docs/drone-critical-points.md`). It doesn't touch the Kerrville driver-rescue demo.

| Real | Simulated (label it) |
|---|---|
| OSM roads (8,372 edges), USGS 3DEP terrain, USGS gauge readings (the Hunt gauge dies at 05:10 CDT), NWS warning times, fire-station locations | Households and their attributes, drone flights, snapshots (generated from the replay), outreach, ungauged creeks ("modeled") |

### REST
| Method | Path | Returns |
|---|---|---|
| GET | `/api/region` | `{id, name, bbox, segments (GeoJSON FC: edge_id, name, highway, bridge), waterways (GeoJSON FC: name, role), gauges[], stations[]}`. Static; fetch once. |
| GET | `/api/region/state` | `{scenario_running, sim_time, alerts[], gauges[], segments: [{edge_id, status, belief_depth_in}] (non-open only), critical_points[] (top 12), nodes[], drones[], counters}` |
| GET | `/api/region/critical-points` | Ranked critical points (below) |
| GET | `/api/region/nodes` | All population nodes (below) |
| GET | `/api/region/drones/plan` | Drones with their current planned tour |
| POST | `/api/demo/start?scenario=hill_country&speed=150` | Starts the replay (01:00 → 07:30 CDT; about 2.5 min at 150×). `scenario` defaults to the Kerrville demo. |
| POST | `/api/demo/reset?scenario=hill_country` | Stops and clears the replay |

### WS events (same `/ws`, envelope `{type, seq, ts, payload}`; every payload has `scenario: "hill_country"`)
| type | payload |
|---|---|
| `region.reset` | `{sim_time}`: clear Hill Country layers |
| `region.alert` | `{id, event, headline, active, simulated: true, at}`: the real NWS timeline, labelled REPLAY |
| `gauge.status` | `{site, name, waterway, lon, lat, online, stage_ft, observed_at, rate_ft_per_hr, change: online/offline}` |
| `region.segments` | `{segments: [{edge_id, status, belief_depth_in}]}`: only changed edges. Status is `open \| unknown \| likely_flooded \| confirmed_flooded` (belief, never truth) |
| `critical_points.ranked` | `{t, points: [CriticalPoint]}` |
| `node.updated` | `Node` |
| `drones.update` | `{t, drones: [Drone]}`: every tick |
| `snapshot.created` | `Snapshot` (overview §9.5) |
| `region.counters` | `{sim_time, households_warned, households_route_out, nodes_cut_off, households_cut_off, points_checked, drone_km, boat_required}` |
| `demo.step` | `{scenario, step 1-7, title, detail, sim_time}` |

**CriticalPoint**: `{id, name, kind: crossing|bridge|low_spot, waterway, lon, lat, p_flooded, status, priority, breakdown: {dependency, vulnerability, p_weight, uncertainty, urgency}, node_ids[], last_snapshot: Snapshot|null}`. Show the breakdown as the "why this point" panel: priority = dependency × vulnerability × p_weight × uncertainty × urgency.

**Node** (an *area*): `{id, name, kind: homes|camp|rv_park, town, lon, lat, households, status: ok|at_risk|partially_cut_off|cut_off, instruction: none|route_out|shelter_in_place|wait_for_check, risk: {score 0-100, band: low|moderate|high|severe, ground: low|mid|high, factors: {access, water, ground, vulnerability} (points, sum = score), height_above_water_m}, unavoidable_points[], optional_points[], rescue: truck_route|boat_required|null, reasons[]}`.

**Area risk (added 2026-11-08):** every area has a score. The objective is to **move people from low, high-risk ground to high ground**: `route_out` always ends on high ground (at least 12 m above the nearest waterway), and the message says "Leave now for high ground by ...". `/api/region/state.nodes` and `/api/region/nodes` are sorted by `risk.score`, highest first. Colour the bands low/moderate/high/severe with the status scale, not brand red. `region.counters.households_by_risk` = `{low, moderate, high, severe}` covers *every* household in the region; homes with no floodable point on any exit count as low. Camps and RV parks use **generic labels** ("Riverside youth camp A, Hunt"). Never show real camp names.

**Drone**: `{id, station, lat, lon, status: idle|flying|snapshot|returning, target, eta_s, battery_pct, tour: [point_id], path: [[lon,lat],...] (planned: drone → stops → station), km_flown, simulated: true}`. Draw `path` dashed (plan) and the trail solid.

**Snapshot**: `{point_id, drone_id, time, water_on_road, road_covered_pct, est_depth_in, depth_method: water_edge_dem|visual, rising, people_seen, confidence, image_url, simulated: true}`.

## Drone vision snapshots (2026-11-08, additive)

Real vision output from the drone pipeline (`backend/vision/`, spec `drone_vision_plan.md`, accuracy in
`vault/Experiments/2026-11-08 Drone vision accuracy.md`).

| Method | Path | Notes |
|---|---|---|
| POST | `/api/snapshots` | Body: `VisionSnapshot` (below). `202 {accepted, fused, not_fused_reason, alerts}`. 403 untrusted origin, 422 invalid, 503 region failed to load. A `cp-*` point fuses into the Hill Country loop only while the replay is running. |
| GET | `/static/drone/snapshots/<file>.jpg` | Annotated snapshot image (water tint, boxes, readout) |
| POST | `/api/region/drones/tello` | (existing, `DRONE_MODE=tello`) The Tello's hover frames now run through the vision model. Response `{ok, vision: true, fused, not_fused_reason, snapshot: VisionSnapshot}` with `source: "live"`, `depth_method: "none"`. If the vision models are not installed (or `TELLO_VISION=0`) it falls back to the old blue-sheet cover: `{ok, vision: false, snapshot: Snapshot}`. Either way `snapshot.created` is emitted. A hover with no water seen gives `water_on_road: null` (unknown), not dry. |

WS: the same `snapshot.created` event as above. The payload is a **superset** of the Hill Country `Snapshot`, so existing readers keep working.

**VisionSnapshot**. The overview §9.5 fields keep their meaning, with these additions:
- `water_on_road: true | false | null`. `null` means not enough road was visible. It is never treated as dry, and fusion ignores it. `false` means most of the road was seen and it's dry. **It never means "safe".**
- `est_depth_in: number | null`. `null` means no depth was measured. There is no fake 0.
- `depth_method: "water_edge_dem" | "none"`:
  - `water_edge_dem`: water edge + elevation map, with a range. **This is the only source of a depth.**
  - `none`: no depth measured (photos, video and live Tello frames have no pose/elevation). `est_depth_in` is `null`.
  - A car's shape is never used as a depth gauge (changed 2026-11-08: `car_reference` was removed).
  - (The simulated loop also sends `"visual"`.)
- `rising: true | false | null`. `null` is the `"unknown"` trend. `false` is steady or falling.
- `road_covered_pct` is the share of the **visible** road under water. `road_visible_pct` says how much road was seen.

New fields:
- `lat, lon`, `drone_id`, `source: synthetic|video|photo|live`, `simulated`
- `water_surface_elev_m`, `water_surface_range_m: [lo, hi]`
- `depth_at_road_range_in: [lo, hi]`
- `depth_band: shallow|caution|dangerous|vehicles_float|boat_only|null` (3/6/12/24 in from `weights.yaml`; there is no "open" band)
- `rise_rate_in_per_hr: number|null` (null unless the trend is significant), `trend: rising|falling|steady|unknown`
- `edge_points_used`, `edge_sides: 0|1|2`
- `vehicles: [{track_id, type, lat, lon, in_water, partly_submerged, depth_at_vehicle_in, band: none|wheels|doors|windows|roof|null, band_source: water_surface|null, matched_case_id}]` (band and depth only when the water surface was measured; otherwise null)
- `people: [{track_id, lat, lon, situation: in_water|on_vehicle|dry_near_water|dry_away, on_vehicle_id}]`
- `alerts: [{priority: critical|high|medium|low, kind, message, track_id, lat, lon, depth_in, boat_required, case_id}]` (sorted most urgent first; `boat_required` is true whenever depth is unknown; an operator confirms before anything reaches 911)
- `spread_segments: [edge_id]`: nearby roads marked `likely_flooded` from this reading, never confirmed
- `confidence_reasons: [string]`

### Live mode (added 2026-11-08): the same detection on real-time Texas feeds

The Hill Country loop runs in one of two modes. **`replay`** (default) is the July 4, 2025 replay above. **`live`** steps the same fusion every 30 s on wall-clock time over live public data for the same region. Both modes feed the loop through one observation layer (`backend/observe/`), so every payload has the same shape.

| Method | Path | Returns |
|---|---|---|
| POST | `/api/region/mode?mode=live\|replay` | `{ok, mode}`. Stops whatever is running, clears the loop, emits `region.reset {scenario, mode}`. Live starts polling and stepping at once. Replay waits for `/api/demo/start?scenario=hill_country`, which also switches back to replay. |
| GET | `/api/region/sources` | `{mode, sources: {id: SourceStatus}}`. Shows which evidence drives detection, where it came from and how old it is. |

**SourceStatus**: `{status: ok|stale|unavailable|pending|not_used, provenance: live|cached|replay|none, as_of (provider observation/product time), checked_at, detail, error}`.
- Detection sources: `usgs_gage`, `nws_alerts`, `mrms`, `lsr`, `nwps`.
- The statewide collectors that don't apply to this region are listed as `not_used`, with the reason in `detail`.
- Show `stale` and `unavailable` prominently. They mean "we can't see", never "all clear".

Additions to `/api/region/state` and the WS events. All are additive; existing fields are unchanged.

| Where | What changed |
|---|---|
| `/api/region/state` | Adds `mode`, `forecasts[]` and `sources`. `scenario_running` is true while the replay or live monitoring runs. |
| `region.alert` | Now `{id, event, level: warning\|watch\|advisory\|statement\|forecast, headline, emergency, simulated, source: replay\|nws\|nwps, at, area, effective, expires, active}`. |
| Alert lifecycle | In live mode an alert is sent once with `active: true` and again with `active: false` when it ends, is cancelled or is superseded. Drop it from the map then. Replay alerts never end. Only `level: warning` sets `in_warning` and lets drones fly; the other levels are context. |
| `gauge.status` / `gauges[]` | Adds `flood_category: none\|action\|minor\|moderate\|major\|null`. It is official NWS stages, for Hunt (HNTT2) and Kerrville (KRRT2) only. |
| `forecasts[]` | `{lid, site, name, observed_ft, observed_at, observed_category, crest_ft, crest_at, crest_category, issued_at, thresholds}`. `crest_*` is null when NWS has no current forecast. |
| Drones in live mode | They get planned `tour`/`path` but stay `idle` at their station. There is no replay truth to simulate a flight from. Draw the path as "recommended tour". `snapshot.created` in live mode comes only from a real drone. |

## Per-user danger (added 2026-11-08, additive): "is this person in danger where they are, right now?"

Backend: `backend/safety/`, tunables in `backend/config/safety.yaml`. It runs on the Hill Country loop in replay
**and** live mode: every loop step (and every location ping) re-assesses each consented user. The steps are:
1. Hazard at their position: roads within 60 m and 400 m, crossings, NWS polygons, gauges, radar, road reports.
2. Their vulnerability, from one profile model.
3. Their motion: parked, driving or stopped.
4. The outreach ladder.

Levels: `none < watch < warning < danger < critical`.

Unknown is never "dry":
- `depth_in: null` means no gauge covers that road.
- `confidence` drops to `medium` or `low` when evidence is missing or stale.

Outside the region only NWS polygon alerts apply, capped at `warning`, or `danger` inside an Emergency polygon.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/safety/summary` | `{mode, ready, users, levels: {none, watch, warning, danger, critical}, degraded_sources, sources}` |
| GET | `/api/users?limit&offset` | `{total, users: [UserPublic]}`. Never includes phone numbers. |
| POST | `/api/users` | Enroll a real user (trusted origin). Body: `{id, name, phone (+E.164), age?, vehicle_type, home_lat, home_lon, contact_name?, contact_phone?, needs[], language: en\|es, preferred_channel: sms\|voice\|app, consent_flood_alerts: true}`. Returns 201 `UserPublic`, 409 if the id is taken, 422 if invalid or no consent. Phones are stored only in gitignored `data/user_registry.json`. |
| GET | `/api/users/at-risk?min_level=warning&limit` | `{mode, total, users: [Assessment + response]}`, most urgent first (level, then vulnerability). |
| GET | `/api/users/{id}/danger` | `Assessment + response`. 409 until the replay or live mode has stepped once. |
| POST | `/api/users/{id}/location` | Trusted origin. Body: `{lat, lon, speed_mps?, heading_deg?, accuracy_m?, ts?}`. Returns `Assessment + response + actions`. Live mode: 422 if `ts` is more than 5 min in the future or more than 1 h old. Replay: pings are stamped with the sim clock. |
| POST | `/api/users/{id}/route` | Trusted origin. Body: `{points: [[lat, lon], ...]}` (2 to 2000 points), the planned trip. Every road on it is checked (a pre-trip warning). Returns `{edges_matched}`. |
| POST | `/api/users/{id}/reply` | Trusted origin. Body: `{reply: safe\|need_help, by: driver\|emergency_contact\|parent}`. Manual or ops reply. Real replies also arrive by SMS or poll through `/api/photon/inbound` or the Photon 2.0 socket, in English or Spanish (SAFE/HELP/BIEN/AYUDA), matched by normalized phone. |
| GET | `/api/region/gauges` | Added 2026-11-08 (additive). The region loop's gauge list only, without segments and points (~2 KB instead of ~140 KB): `[{site, name, waterway, lon, lat, online, stage_ft, observed_at (epoch s), flood_category\|null, rate_ft_per_hr}]`. Polled by the phone app. |
| GET | `/api/region/flood-layer?bbox=minLon,minLat,maxLon,maxLat` | Added 2026-11-08. The phone's flood map. One window (max 0.6° each way, else 422): `{at, mode, bbox, segments: [{id, status, name, coords}], points: [{id, name, kind, status, lon, lat}], gauges: [...], alerts: [{id, headline, level, emergency}]}`. Segments are non-open roads only (open is the base map), directed pairs merged, worst status wins. Unknown points are `unknown`, never `open`. |
| GET | `/api/users/{id}/directions` | Added 2026-11-08. A way to higher ground from the user's last position: `{text, kind: route\|stay\|none, road_names, length_m, coords: [[[lon,lat],...],...], avoid}`. Same router as the region's route-out (confirmed-flooded crossings removed). Never called "safe". |
| POST | `/api/users/{id}/assistant` | Added 2026-11-08. Trusted origin (+ `SAFETY_API_KEY` if set). Prepares the inbound assistant line: with `HITIDE_ASSISTANT_LIVE=1` it writes the user's situation + directions into the ElevenLabs agent's default variables, returns `{mode: "live", phone, directions, response}` and watches the agent's conversations; a "need help" outcome flags responders. Otherwise `{mode: "mock", phone: null, ...}` and a simulated timeline entry. Timeline entries: `assistant call requested[ (simulated)]`, `assistant call: <summary>`, `assistant line unavailable`, `assistant call not detected`. |
| GET | `/api/routes/options?start=lon,lat&end=lon,lat` | Added 2026-11-08. Up to 3 different ways (422 outside the region): `{at, options: [{id, label: Fastest\|Avoids confirmed flooding\|Another way, via, length_m, minutes, status: flooded\|likely\|clear, flooded, likely, unknown_roads, coords}]}`. Ordered least reported flooding first (clear, likely, flooded; then time). "Fastest" may cross water (shown, never hidden, and sorted down); the others drop confirmed-flooded roads and penalize likely/unknown, and differ by road. `clear` means "no flooding reported", never safe. |

**Assessment**:
- Top-level fields:
  - `user_id`
  - `level`
  - `hazard_level` (evidence only)
  - `bumped_for_vulnerability`
  - `reasons[]` (plain sentences, worst first)
  - `advice`: `turn_around | do_not_drive | move_to_high_ground | stay_on_high_ground | be_ready | none`
  - `confidence`: `high | medium | low`
  - `stopped_in_water`
  - `location_stale`
  - `assessed_at`
- `location`: `{lat, lon, ts, state: parked|driving|stopped, speed_mps, heading_deg}`
- `hazard`:
  - Coverage and position: `coverage: region|alerts_only`, `edge_id`, `road_name`, `distance_to_road_m`, `waterway`, `height_above_water_m`.
  - Water: `depth_in|null`, `max_depth_nearby_in|null`, `unknown_nearby`.
  - `worst_point: {id, name, kind, waterway, status, p, distance_m, on_my_road}`.
  - Alerts: `in_warning`, `in_emergency`, `emergency_polygon`, `in_watch`, `alert_headlines[]`.
  - Other evidence: `rain_in_hr`, `gauge_rising`, `gauge_category`, `forecast_category`, `closure_nearby`, `far_from_water`, `degraded_sources[]`.
  - Road hits: `ahead[]` and `route[]`, each `{edge_id, road_name, distance_m, depth_in, point_status}`.
- `vulnerability`: `{score, band, stall_depth_in, needs_priority, is_teen, is_older, channel, no_voice, language, reasons[], factors}`.

**response**: `{episode_level, awaiting_reply, called, call_unanswered, family_contacted, responders_flagged, case_open, need_help, safe_until, timeline: [{t, what}]}`.

**Ladder**:

| Level | What happens |
|---|---|
| watch | A text. |
| warning | A text (spoken in-app while driving), plus a copy to a teen's parent. |
| danger | A safe/help poll. No reply → a voice call. No answer or voicemail → the emergency contact gets a text and a call. |
| critical | A call now, and a case opens. Family and responders follow after 2 min (immediately if highly vulnerable). |

- **When we notify:** only when the level rises, or at most once per level after its cooldown. A SAFE reply mutes the level for 30 min; HELP flags responders and stops the polls.
- **All clear:** once the level has stayed below warning for 15 min, one "all clear" message is sent.
- **Wording:** messages are in English or Spanish, and never call a road safe.

**Mobile consumer** (`mobile/src/data/live/`, added 2026-11-08):
- The phone app is one user (`hc-dana`, Dana Whitfield, sim-only phones).
- It reads `GET /danger` every 5 s and refetches on `user.danger` for its own `user_id`. A 409 (no flood picture yet) shows "Connecting". Network errors and 5xx show "Offline".
- Every 30 s it also reads `GET /api/safety/summary` (`mode` only) and `GET /api/region/gauges` (Kerrville, site 08166200).
- It reads `hazard.degraded_sources` and `confidence: low` as "can't fully check", never as clear.
- It writes `/reply` (`by: driver`), `/route`, and `/location`. Location writes come from the developer demo drive only.
- It validates every payload with zod and ignores fields it does not use.
- Timeline strings it matches: `critical|danger -> …poll|voice|open_case`, `HELP from `, `family contacted`, `responders flagged`, `SAFE from <who>` (exact), `all clear` (episode boundary). Changing that wording is a contract change.

**WS events**:
- `user.danger`: `{user: UserPublic, ...Assessment}`, sent only when the level or top reason changes.
- `user.responders`: `{user_id, level, reasons, location}`.
- `user.case`: `{user_id, level, reasons}`.
- `user.call`: `{user_id, recipient, answered, reply, summary}`.

**Outreach events**:
- `outreach.status` gains `"suppressed"`: live mode, but the number isn't allowlisted. It used to be logged as a fake `"sent"`.
- Real sends go only to `env:DEMO_PHONE_*` numbers, or to enrolled +E.164 users when `OUTREACH_ALLOW_ENROLLED=1`.

## SpacetimeDB live tables (added 2026-11-08, additive)

SpacetimeDB is now the primary database (see `docs/SPACETIMEDB.md`). Besides the REST/WS API above, the frontend may **subscribe directly** to the public tables for live row updates (no polling):

- **Server:** local `ws://127.0.0.1:3000`. Use the WebSocket subprotocol `v1.json.spacetimedb` on `/v1/database/floodwatch/subscribe`, or the `spacetimedb` npm SDK.
- **Query shape:** subscriptions must be `SELECT * FROM <table> [WHERE ...]`. Column projections aren't allowed.
- **Field names:** snake_case.
- **Options:** encoded `{"some": v}` / `{"none": []}`.
- **Timestamps:** encoded `{"__timestamp_micros_since_unix_epoch__": n}`.

| Table | Use |
|---|---|
| `danger_latest` | One row per person: `user_id, level, hazard_level, top_reason, advice, confidence, lat?, lon?, vulnerability_band, mode, assessed_at, updated_at`. Position only for simulated users, or real users at danger or above, rounded to about 1 km. Example: `SELECT * FROM danger_latest WHERE level = 'critical'` |
| `app_user` | People: no phones. Enrolled users show first name only, no age, no tags, and a rounded home |
| `source`, `ingestion_run` | Data sources and their fetch health |

Outreach, cases, drone snapshots and evidence stay on the REST/WS API above. Those tables are private because they can identify or locate people.

- **Private tables** are not visible to clients: `user_contact`, `user_profile`, `user_track`, `response_state`, `outreach_event`, `escalation_case`, `vision_snapshot`, `observation`, `raw_record`, `setting`, `inspection_task`, `kv`, `config`.
- **All writes go through the backend.** The module rejects reducer calls from any identity but the backend's.
- `/api/health` gains `database: {backend, requested, fallback_reason, writes: {queued, failed, dropped, last_error}, spacetime: {url, database, authenticated}}`, and `modes.db` is the backend actually in use. That reads `spacetime`, or `sqlite (fallback: …)` when SpacetimeDB isn't running.
The statewide recent response now includes regional sensors, NOAA rainfall/runoff grids and NWPS stations, crossing statuses, camera context and TranStar access markers. Source batches add label, notes, errors and context fields. Admitted records may include a preview object with title, detail, provider-derived time, timestamp_role, evidence_type, geometry, optional value/unit and safe public link. Context records have unverified freshness and require an explicit UI opt-in. The raw payload and envelope remain available independently of the preview.

## Live drone (real DJI Tello)

> Added 2026-11-08. Separate from the **simulated** drone above (`drone.update`, `DroneState`, `/static/drone/*`), which stays as is. Design notes: [tello-drone-handoff.md](tello-drone-handoff.md).

The backend does not talk to the drone itself. It forwards to the **Tello bridge** (`backend/scripts/tello_dashboard.py`, its own venv, `http://127.0.0.1:8765`, override with `TELLO_BRIDGE_URL`). When the bridge isn't running, `bridge` is `"offline"` and the UI shows `fallback_image_url`, labelled as cached footage. The offline demo never needs a drone.

| Method | Path | Returns / body |
|---|---|---|
| GET | `/api/live-drone/status` | `LiveDroneStatus` (below). Poll about once a second. Always 200. |
| GET | `/api/live-drone/video` | MJPEG stream (`multipart/x-mixed-replace`) for an `<img src>`. 503 when the bridge is offline. |
| POST | `/api/live-drone/action/{action}` | `action` is `takeoff`, `land` or `emergency`. Returns `{"result": "ok"}` or `{"result": "<reason it was refused>"}`. 503 when the bridge is offline. |
| POST | `/api/live-drone/rc` | body `{"lr","fb","ud","yaw"}`, each an int from -100 to 100. Resend every 200 ms while held; the drone hovers if nothing arrives for 0.6 s. |

POSTs use the same trusted-origin guard as the other state-changing routes.

`LiveDroneStatus`:

```json
{"bridge": "online", "fallback_image_url": "/static/drone/flood_03.jpg", "controls_url": "http://127.0.0.1:8765",
 "connected": true, "flying": false, "busy": "", "battery": 88, "temp": 61, "height": 0, "tof": 10,
 "flight_time": 0, "speed": [0, 0, 0], "attitude": [0, 0, 0], "state_age": 0.2, "video_age": 0.1,
 "log": ["05:47:09  Takeoff done, hovering"]}
```

- `bridge`: `online` (the bridge answered) or `offline` (everything after `controls_url` is absent).
- `connected`: the bridge is receiving telemetry from the drone right now. False means show "link lost"; values are the last known ones.
- `busy`: `""`, `"takeoff"` or `"land"`. **Land is always allowed**, including during takeoff.
- `video_age`: seconds since the last frame, or null before any video.

### Gauge tray water level

> Added 2026-11-08. Design: [gauge-water-level-plan.md](gauge-water-level-plan.md). The bridge reads the flood depth off the printed gauge tray in the Tello camera view (`backend/gauge/`, runs in the bridge venv). The backend only forwards.

| Method | Path | Returns / body |
|---|---|---|
| GET | `/api/live-drone/gauge` | `GaugeStatus` (below). Poll about once a second. Always 200. |
| POST | `/api/live-drone/gauge/baseline` | Captures the dry baseline from the current frame (pour no water yet, same camera pose as the readings). Returns `{"result": "ok"}` or `{"result": "<why it was refused>"}`, for example `"tray already has water; capture the baseline dry"`. UIs show "Dry baseline captured" or the refusal reason. |
| POST | `/api/live-drone/gauge/start` | Starts reading at about 2 Hz. Returns `{"result": "ok"}` or a reason (for example the gauge module is unavailable). |
| POST | `/api/live-drone/gauge/corners` | **Tag-free pose.** Body `{"points": [[x, y], [x, y], [x, y], [x, y]]}` (the 4 rim-top corners in frame pixels, starting at the left end of the FLOOD WATCH edge and going round) or `{"clear": true}`. Returns `{"result": "ok"}` or why it was refused. 422 for a malformed body. |
| POST | `/api/live-drone/gauge/stop` | Stops reading; the last estimate stays visible. Returns `{"result": "ok"}`. |
| GET | `/api/live-drone/gauge/overlay.jpg` | The latest annotated frame (tags, wet cells tinted, level text) as `image/jpeg`, `Cache-Control: no-store`. 404 before the first reading, 503 when the bridge is offline. Reload with a cache-busting query (`?t=...`). |

POSTs use the trusted-origin guard and return 503 when the bridge is offline, or 504 when it is running but did not answer within 8 s. While the bridge is still loading the gauge model, `baseline` and `start` answer at once with `{"result": "loading the gauge model, try again in a moment"}`.

`GaugeStatus` (the bridge's `WaterEstimate.to_dict()` fields, flat, plus service state):

```json
{"gauge": "online", "enabled": true, "running": true, "error": null, "age_s": 0.4,
 "level_mm": 9.0, "level_mm_range": [8.0, 10.0], "ft": 2.5, "ft_range": [2.0, 3.0], "confidence": 0.82,
 "crossing_flooded": true, "car_level": "doors", "houses_flooded": 4, "houses_total": 10,
 "visible_cells": 18240, "wet_cells": 6120, "wet_fraction": 0.34, "tags_seen": 4, "reproj_err_px": 0.9,
 "has_baseline": true, "baseline_moved": false, "simulated": false, "reason": null, "ts": 1762600000.0,
 "pose_source": "tags", "corners": null}
```

- `gauge`: `online` (the bridge answered and the gauge module loaded), `unavailable` (the bridge runs but `backend/gauge` failed to import; `error` says why; video and flight still work), or `offline` (no bridge; every other field is absent).
- `enabled`: reading was started with `/gauge/start`. `running`: the reader thread is alive and producing estimates.
- `error`: the last import, reader or overlay-encode error, or null. On a reader error the last estimate stays in the payload; `age_s` grows, so the UI shows it as stale.
- `pose_source`: where the camera pose came from: `tags` (ArUco), `corners` (the 4 clicked rim corners) or `rim` (the automatically detected tray outline, accepted only when one orientation clearly fits). Null when there is no pose. Tags win when at least 3 are readable. `corners`: the clicked points, or null.
- `age_s`: seconds since `ts` (the last reading), or null before any reading. **When `age_s` > 5 or `running` is false, dim the reading and show "Last reading Ns ago"**: it is not live.
- Estimate fields are null until the first reading. **`ft` is null when the evidence is weak** (fewer than 3 tags, high reprojection error, too few visible cells, flat score) and `reason` then says why: show the reason, never a guess. `reason` can also be set on a valid reading (a caveat); **show `reason` whenever it is non-null.**
- **Always show the range** (`ft_range`) next to `ft`. Each tray terrace step is 1 ft of rise above the normal pool. The reading resolves which step the water is in: `ft_range` is that step's bounds and `ft` is its centre (water between the 2 ft and 3 ft terraces reads `"ft": 2.5, "ft_range": [2.0, 3.0]`).
- `"ft": 0` with `"ft_range": [0, 0]` means the water is at or below the normal pool: show "At or below normal pool", not "0–0 ft".
- `baseline_moved`: true when the camera moved since the dry baseline, so the reader ignores the baseline and uses the dye colour only (lower confidence). Show "Camera moved, using dye only" in place of "Captured" for the dry baseline.
- `wet_fraction`: 0 to 1, wet cells over visible cells in the current frame (a diagnostic).
- `car_level`: `none`, `wheels`, `doors`, `windows` or `roof` (the `VisionResult.water_level` vocabulary), or null.
- `confidence`: 0 to 1; capped lower when `has_baseline` is false (dye-hue only).
- `simulated`: true when the frame was synthetic (`gauge.synth`); label it "SIMULATED" in the UI.
