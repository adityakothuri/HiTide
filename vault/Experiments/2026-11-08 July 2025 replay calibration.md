---
tags: [hitide, experiment, hill-country]
status: done
updated: 2026-11-08
---

# 2026-11-08 July 2025 replay: calibration and counterfactual

**Goal:** check the Hill Country flood model against what really happened on July 4, 2025, and measure what the drones add. See [[Critical Point Drones]] and `docs/drone-critical-points.md`.

## Inputs (real)

- 5 USGS gauge series fetched by `scripts/fetch_july2025.py`. The peaks match the research exactly: Hunt 37.52 ft at 10:10Z, then silence; Kerrville 37.51 ft at 11:45Z; N Fork 21.2; Johnson Ck 12.54; abv Bear Ck 34.4.
- Fitted flood-wave speed: **2.83 m/s** (Hunt → Kerrville peak times).

## Calibration

| Check | Model | Real | Verdict |
|---|---|---|---|
| Roads flooded before the rise (01:00–02:00) | 0 (after the "ford" fix; 30 before it) | 0 | ok |
| First SH 39 segment in Hunt ≥ 6 in | 03:15 | "under water by 04:22" (KSAT) | consistent; the report is an upper bound |
| First Kerrville road ≥ 6 in | 04:25 | gauge minor flood 05:45 | low park and creek roads flood below flood stage; plausible |
| Hunt gauge after it died | truth continues (crest about 37.5 ft, 28.7 ft by 07:30); belief unknown from 05:41 | gauge destroyed | ok (fixed a CRITICAL where the gap fill never ran) |

## Counterfactual (`uv run python -m scripts.replay_report`)

| Measure (same 3 drones, same night) | Priority planner | Naive patrol (stalest-first sweep) | Gauges only, no drones |
|---|---|---|---|
| Flooded chokepoints (some area's only exit), 243 households behind them | 12 | 12 | 12 |
| Households whose chokepoint a drone confirmed flooded | **186 (77 %)** | 7 (3 %) | n/a |
| Flooded crossings known at all (of 69) | 33 by drone | (not measured) | 21 (mostly gauged main stem) |
| Flooded South Fork / Cypress Creek crossings flagged | most, 2–90 min after the water | | almost none |
| First area told to shelter | **02:17 CDT, 107 min before the real 04:04 Flash Flood Emergency for Hunt** | | |

Reading it honestly:
- On the gauged main stem, gauges alone flag crossings early (the median is 67 min before the water, because the rules are cautious). Drones add little there.
- On the ungauged forks, where the camps were, nothing but a drone ever sees the water.
- The planner's advantage over a patrol isn't more checks. It checks the crossings that people's only way out depends on.

## What broke and was fixed on the way

- The demo runner cancelled its own task, so it emitted nothing. A regression test covers it now.
- Gap fill anchored on the end of the series instead of the outage. CRITICAL from python-reviewer.
- Belief read gauges up to 79 min into the future. HIGH, fixed with causal reads.
- Copying the 8k-edge graph per cut test caused 4.8 s stalls. Now a shared sink graph is used, and the worst step is 2.2 s.
