# Flood Watch API contract (backend ⇄ frontend)

> This contract covers the legacy driver-rescue REST/WebSocket workflow.
> The new `/api/evidence/*` endpoints, operations polling, request examples, and
> persistence requirements are documented in [State of the Union, section 10](STATE_OF_THE_UNION.md#10-api-inventory).
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

**Segment ids:** segments are *directed* edges, so a two-way street appears twice (`u-v-0` and `v-u-0`) with the same geometry. Draw both or dedupe by geometry. Colour each one by its status from the latest `segments.update`. Any id that isn't listed is `open`.

## Privacy and security behaviour (2026-11-07)

- **Before a warning is active**, the snapshot has `drivers: []` and `drivers_opted_in: 100`, and no `drivers.update` events are sent. Locations appear once the `alert` arrives (opt-in terms).
- `urgency_reasons` use coarse bands ("older driver (65+)", "low-clearance vehicle"), never exact age or model.
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
| `drivers.update` | `{drivers:[{id,name,lat,lon,heading_deg,situation,is_demo,urgency}]}` | Move markers. `situation`: parked, planning, driving, stopped_in_water. |
| `alert` | `{id,event,headline,active,simulated,polygon}` | NWS banner + driver "Flood Watch active" status |
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
| REST | `POST /api/drones/{id}/command` body `{"command": "speak"\|"drop_jacket"\|"return"}` → emits `case.update` (+ `drone.update` for return) | Drone actions in the console | The UI adds a local timeline row labelled simulated |
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

**Snapshot**: `{point_id, drone_id, time, water_on_road, road_covered_pct, est_depth_in, depth_method: car_reference|visual, rising, people_seen, confidence, image_url, simulated: true}`.

### Live mode (added 2026-11-08): the same detection on real-time Texas feeds

The Hill Country loop runs in one of two modes. **`replay`** (default) is the July 4, 2025 replay above. **`live`** steps the same fusion every 30 s on wall-clock time over live public data for the same region. Both modes feed the loop through one observation layer (`backend/observe/`), so every payload has the same shape.

| Method | Path | Returns |
|---|---|---|
| POST | `/api/region/mode?mode=live\|replay` | `{ok, mode}`. Stops whatever is running, clears the loop, emits `region.reset {scenario, mode}`. Live starts polling and stepping at once. `mode=live` while live is running is a no-op. A live (re)start within 15 s of the last one returns 429, and so does `/api/demo/reset?scenario=hill_country` in live mode. Replay waits for `/api/demo/start?scenario=hill_country`, which also switches back to replay. |
| GET | `/api/region/sources` | `{mode, sources: {id: SourceStatus}}`. Shows which evidence drives detection, where it came from and how old it is. |

**SourceStatus**: `{status: ok|stale|unavailable|pending|not_used, provenance: live|cached|replay|none, as_of (provider observation/product time), checked_at, detail, error}`.
- Detection sources: `usgs_gage`, `nws_alerts`, `mrms`, `lsr`, `nwps`.
- The statewide collectors that don't apply to this region are listed as `not_used`, with the reason in `detail`.
- Show `stale` and `unavailable` prominently. They mean "we can't see", never "all clear".

Additions to `/api/region/state` and the WS events. All are additive; existing fields are unchanged.

| Where | What changed |
|---|---|
| `/api/region/state` | Adds `mode`, `forecasts[]` and `sources`. `scenario_running` is true while the replay or live monitoring runs. |
| `region.alert` | Now `{id, event, level: warning\|watch\|advisory\|statement\|forecast, headline, emergency, simulated, source: replay\|nws\|nwps, at, area, event_key, effective, expires, active}`. `event_key` is the NWS event (VTEC). Key your map on it, not on `id`: a routine update keeps the same `event_key` and a new `id`. |
| Alert lifecycle | In live mode an alert is sent once per event (`event_key`) with `active: true`, and again with `active: false` when it ends or is cancelled. Updates to the same event don't resend it. Drop it from the map then. Replay alerts never end. Only `level: warning` sets `in_warning` and lets drones fly; the other levels are context. |
| `gauge.status` / `gauges[]` | Adds `flood_category: none\|action\|minor\|moderate\|major\|null`. It is official NWS stages, for Hunt (HNTT2) and Kerrville (KRRT2) only. |
| `forecasts[]` | `{lid, site, name, observed_ft, observed_at, observed_category, crest_ft, crest_at, crest_category, issued_at, thresholds}`. `crest_*` is null when NWS has no current forecast. |
| Drones in live mode | They get planned `tour`/`path` but stay `idle` at their station. There is no replay truth to simulate a flight from. Draw the path as "recommended tour". `snapshot.created` in live mode comes only from a real drone. |
