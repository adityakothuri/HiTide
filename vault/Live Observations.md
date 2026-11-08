---
tags: [floodwatch, module, live]
updated: 2026-11-08
---

# Live Observations

`backend/observe/` is the only way external evidence reaches Hill Country detection (`critical/loop.py`).

```
replay (observe/replay.py)  ─┐
                             ├─> ObservationFrame ─> CriticalLoop._step ─> fusion Signals ─> p_flooded / status
live   (observe/live.py)    ─┘   {flood, alerts, rain_in_hr, closures, forecasts, sources}
```

## Frame field → fusion signal

| Frame | Signal |
|---|---|
| `flood` (RegionFlood from live USGS series) | `model_above_road`, `gauge_rising` |
| `alerts` (level `warning`, covering the point) | `in_warning` (per point now, not region-wide) |
| `rain_in_hr` ≥ `fusion.heavy_rain_in_hr` (1.0) | `heavy_rain` |
| `closures` (NWS storm reports) | `closure` |
| `forecasts` | context alert only |

## Correctness rules

- A failed fetch keeps the last good data, marked `stale`. It never becomes "no warning / no rain / dry".
- Data ages out by its own timestamps: alert `ends`, MRMS valid time, report time, gauge reading time.
- Missing evidence is `None`. MRMS sentinels −1/−3 are not zero.
- Retrieval time never stands in for observation time.
- An NWS Update supersedes and a Cancel removes the message it references. Test messages are dropped. Validity runs on `ends`, else `expires`, never on "sent within 30 min".
- Same 30-min gauge offline rule as the replay.

## Verification (2026-11-08)

- **Replay bit-for-bit.** The golden digest of p, status, node states, counters and alerts per minute matches for 391 steps × 2 policies (`tests/test_replay_golden.py`, `RUN_SLOW=1`). The `scripts.replay_report` output is identical: 77% vs 3% of chokepoint households, 107 min before the FF Emergency.
- **Live path on July 2025 data.** The real hydrographs, run as USGS JSON through `usgs_series` → `build_hydro` → live `RegionFlood`, reach the same 1,105 edges at 6 in or more, with none missed and none extra. With a plain minimum baseline the result is identical (0.00 in). With the despiked baseline (minimum of a 3-point running median) the maximum difference is 0.12 in, from a 0.01 ft shift at 08166140; one borderline edge crosses 6 in up to 15 min later. A 2nd-percentile baseline was tried and rejected (later detection).
- **45-min gap rejected.** A 45-min offline gap (tried for telemetry latency) changed belief by up to 137 in and missed 6 edges. Latency is handled with 2-min polling instead.
- **Live smoke test.** All 5 sources `ok` from real feeds. Stages matched USGS (Hunt 7.77 ft, Kerrville 1.45 ft). A quiet night gave no false flooding (all p = 0.02). It stepped every 30 s, and the replay ↔ live switch worked over the API.

## Review fixes (python, fastapi, domain reviewers)

- Malformed 200 responses for alerts or storm reports are treated as failures, not "zero alerts". A failed NWPS forecast fetch keeps the last forecast.
- A Flash Flood Statement that updates a warning keeps warning level. A forecast more than 24 h old, or marked `fcst_not_current`, raises no forecast alert.
- Storm reports saying the water receded or the road reopened are not closures. A malformed report geometry is skipped.
- Source health is evaluated against data age at read time: MRMS stale after 20 min, USGS stale when no gauge is online.
- `/api/demo/start` and the mode switch share one lock, so replay and live can't run together. The live task logs failures, and shutdown cancels a build that is still starting.

## Stress test and audit (2026-11-08)

How it was tested:
- **Chaos harness.** 4 seeds × 4 simulated hours. About 35% of responses were bad (503, a 200 with an error body, HTML, wrong types, junk features) and 5% of fetches raised. No invariant broke:
  - a warning covers its points until its own end;
  - rain is the last good grid's value or None, never a made-up 0;
  - the hydro revision only increases;
  - every step runs.
  
  Before the fix below, it found one real bug: a single bad 200 response dropped an active warning.
- **Server load.** The server ran on real feeds with 40 concurrent readers and 2 clients randomly toggling mode, start and reset for 60 s.
  - 26,463 GETs, all 200: p50 83 ms, p99 230 ms.
  - 0 errors in the log.
  - All 5 sources `ok` afterwards and live stepping.
- **Independent reviews.** A security reviewer and a detection-correctness auditor, both working on real feed data.

Fixes:
- **A warning that silently drops out is held for 4 minutes.** This covers a warning that leaves one response with no Cancel or Update naming it. A Cancel still drops it at once.
- **Alerts are keyed by NWS event (VTEC).** A routine update (CON/EXT) is no longer shown as the warning ending and restarting. Payloads add `event_key`.
- **Telemetry latency.** USGS readings arrive 7–22 min late; the median is 9–14 min. Measured on July 4, 2025 with readings delayed 12 min, at 06:45 CDT:

  | | Flooded edges |
  |---|---|
  | Modeled truth | 975 |
  | Live, holding the last reading flat | 698 |
  | Live, rising reading carried forward by its own rate (up to 10 min) | 958 |

  Over the whole event against modeled truth, missed edge-minutes fall 13% (34,831 → 30,381) and over-calls rise (3,436 → 7,259). It projects rises only, so it errs toward "flooded". This applies in live only; the replay is unchanged.
- **Gauges go offline after 45 min in live** (30 min in replay). This removes quiet-day flapping (about 3 false offline events a day). With a 20-min delay it also cuts missed edges (8,622 → 6,025 edge-minutes).
- **Live ranking urgency is causal.** It uses the readings available now, carrying rising ones forward 1 h. Before this, live urgency was always off.
- **Live starts on an empty gauge model.** July 2025 stages never show before the first USGS poll.
- **Download caps.** MRMS downloads are capped at 20 MB and the gunzip at 100 MB.
- **Mode switching is throttled.** `mode=live` while already live is a no-op. A live (re)start within 15 s returns 429, so the endpoint can't hammer NWS or USGS.
- **Fetch failures log without tracebacks.**

## Live-mode limits and open decisions

- Drones plan tours but don't fly in sim, because there is no replay truth. Real snapshots (Tello / [[Drone Vision]] bridge) still feed `loop.obs`.
- **Rain is point-local.** It is radar-only QPE, and headwater rain upstream (the July 4 pattern) is not attributed downstream.
- **Outside a warning, fusion ignores gauge, model and rain evidence** (`prior_outside`). This is a pre-existing design choice. Before the first warning, a crossing with modeled water stays "open" while the map segment shows likely-flooded. *Decision pending: it changes the replay results.*
- **The replay's ranking urgency reads the recorded series 1 h ahead,** which is look-ahead. Live is now causal, but replay is unchanged to keep the documented 77% vs 3% result. *Decision pending.*
- **`rate_ft_per_hr` divides by `max(1 h, span)`.** It under-reports when the newest reading is old (a true 2.0 ft/h reads as 1.5 ft/h at 15 min old). *Decision pending: it changes the replay.*
- **The 7-day minimum baseline** can sit high after an event that has stayed elevated for 7 days or more, or after a short window. That would under-call. A single high spike in the current reading isn't filtered.
- Region is Kerr County only (Hunt → Kerrville).

Related: [[Data Sources]] · [[Critical Point Drones]] · [[Flood Simulation]]
