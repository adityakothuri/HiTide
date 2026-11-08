---
tags: [floodwatch, decisions]
status: in-progress
updated: 2026-11-07
---

# Decisions

Dated log. Add a new entry at the top when a decision changes the plan. Keep the reason, not just the choice.

## 2026-11-07: Road status thresholds from NWS TADD table

- Thresholds: caution 3 in, closed 6 in, float 12 in, boat 24 in.
- Source: [NWS Turn Around Don't Drown](https://www.weather.gov/safety/flood-turn-around-dont-drown).
- Stored in `road_status_in` in `backend/config/weights.yaml`, not hard-coded.
- Caution at 3 in is our own band. The NWS page does not define it.
- Related: [[Risk Scoring]]

## 2026-11-07: Hand-traced river fallback if Overpass is unreachable

- If every Overpass mirror fails, the build uses a hand-traced Guadalupe River centerline (`RIVER_FALLBACK` in `backend/scripts/build_town_cache.py`).
- Reason: the demo must run offline, and Overpass was unreachable during the first run.
- Related: [[2026-11-07 Town cache build]], [[Flood Simulation]]

## 2026-11-07: Outreach adapter with mock mode because no Photon creds yet

- Every outbound action goes through one adapter. `PHOTON_MODE=mock` logs and streams to the UI. `photon` sends for real.
- Reason: no Photon creds yet. The demo must not depend on Photon.
- Related: [[Photon Outreach]]

## 2026-11-07: Python 3.12 via uv because system Python 3.15 lacks geo and ML wheels

- `backend/.python-version` pins 3.12. `uv` manages the venv and lockfile (`backend/uv.lock`).
- Reason: the system Python is 3.15, which likely has no torch, ultralytics, or osmnx wheels.
- Related: [[Architecture]]

## 2026-11-07: Photon Stable (Spectrum) chosen

- Photon Spectrum (Stable) is the Photon version we use.
- Reason: it is the only version that documents polls, read receipts, and outbound SIP voice on an iMessage line.
- Related: [[Photon Outreach]], [[Data Sources]]

## 2026-11-07: Photon sends go through a Node sidecar
Spectrum's REST OpenAPI has no send or poll endpoint. Only `spectrum-ts` can send. We added `photon-sidecar/` (about 80 lines) exposing `/send` and `/poll`, and it forwards inbound replies to `/api/photon/inbound`. The Python adapter talks to the sidecar.

## 2026-11-07: Demo clock, fast-forward then 1x
At 60x, the 12 s escalation timers would last 0.2 s on screen and cars would teleport. The scenario ramps the flood at 300x to minute 35 (about 7 s), then runs at 1x so the timers and driving are real-time. Suggested by the planner agent.

## 2026-11-07: Two meanings of "moving"
Pre-trip texts skip any driver **on a trip** (`DriverMotion.moving`). The outreach guard blocks text, poll and voice only when the car is **physically moving** (speed ≥ 0.5 m/s). A car stalled in water must still get the "Are you okay?" call.

## 2026-11-07: Est. claims avoided is an estimate
(warned + rerouted) × avg vehicle flood claim × 10% (the assumed share who would have driven into water). The placeholder average is $15k. It needs a source before the pitch.

## 2026-11-07: Move outreach to Photon 2.0 (beta)
The Photon track requires 2.0, and we had built on Stable. 2.0 has a plain REST API (users → spaces → messages), so Python calls it directly. Inbound arrives over Socket.IO, so there's no tunnel. `PHOTON_MODE=mock|stable|photon2`, and Stable stays as the fallback.

## 2026-11-07: Voice = ElevenLabs agent over Photon SIP, set up by script
Voice runs on the Photon SMS number (iMessage lines can't take calls on a shared line). `scripts/elevenlabs_setup.py` creates the agent and imports the number through the API, because the dashboard UI kept changing. The first message is the `{{opening_line}}` variable, since first-message overrides were rejected on SIP calls.

## 2026-11-07: Calls run in the background; voicemail counts as no answer
Call setup takes 10–20 s, so the call never blocks the sim tick. The transcript watcher starts when the call ID arrives. Voicemail detection leaves one message and hangs up, and escalation continues.

## 2026-11-07: Margaret's demo phone = Teammate B
B gets no texts during the demo (B is the moving driver), so B's phone ringing as "Margaret" at step 4 is the live voice moment. Change `demo-d.phone` in `data/drivers.json` to reassign it.

