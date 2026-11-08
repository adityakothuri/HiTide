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
