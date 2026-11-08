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

### Expanded source previews

The statewide recent response now includes regional sensors, NOAA rainfall/runoff grids and NWPS stations, crossing statuses, camera context and TranStar access markers. Source batches add label, notes, errors and context fields. Admitted records may include a preview object with title, detail, provider-derived time, timestamp_role, evidence_type, geometry, optional value/unit and safe public link. Context records have unverified freshness and require an explicit UI opt-in. The raw payload and envelope remain available independently of the preview.
