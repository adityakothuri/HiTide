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

## Live-mode limits

- Drones plan tours but don't fly in sim, because there is no replay truth. Real snapshots (Tello / [[Drone Vision]] bridge) still feed `loop.obs`.
- **Gauge flapping.** With 15-min recording and 7-22 min telemetry lag, a quiet-period reading can be about 37 min old, and the gauge then counts offline (30-min rule). USGS records every 5 min at most region gauges today. A gap rule longer than 30 min was measured to hurt accuracy.
- **Rain is point-local.** It is radar-only QPE (no gauge correction), and headwater rain upstream (the July 4 pattern) is not attributed downstream. It adds only `add_heavy_rain` (0.15).
- An NWS Update gets a new id, so the UI sees `active:false` for the old message and `active:true` for the new one.
- Region is Kerr County only (Hunt → Kerrville). Other statewide sources are `not_used`, each with a reason.

Related: [[Data Sources]] · [[Critical Point Drones]] · [[Flood Simulation]]
