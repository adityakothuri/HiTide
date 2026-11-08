# Drone critical-point optimization: how it works and why

This document consolidates three sources:
- `overview.md` §6–§10 (ground truth),
- the colleague's evidence and connectivity work (`backend/evidence/analysis.py`, `docs/history/2026-11-07-evidence-milestone.md` §8),
- the Hill Country implementation (`backend/critical/`, `backend/drone/planner.py`).

It ends with the July 4, 2025 replay results. Code references are `file:function`.

## 0. The question each flight must answer

A drone flight is worth flying only if its answer can change what we tell people.

Every quantity below serves that one test, applied to a road network, a population and a rising river:
- which crossings people depend on,
- how unsure we are about each one,
- how many people and how vulnerable they are,
- how fast the answer goes stale.

## 1. The map and the water (real-ish data)

| Layer | Source | Code |
|---|---|---|
| Roads | OSM drive network, bbox 29.97–30.12 N, −99.45 to −99.10 W (Hunt → Ingram → Kerrville), 8,372 directed edges | `scripts/build_region_cache.py` |
| Terrain | USGS 3DEP 10 m for road elevation; 30 m max-pooled grid for drone clearance | same |
| Waterways | Guadalupe main stem (33 km), North and South Forks, Johnson, Cypress, Town, Third, Camp Meeting and Quinlan creeks, plus 250 unnamed-stream crossings | `sim/region.py` |
| Gauges | 5 real USGS series, July 3–5, 2025, parameter 00065 | `scripts/fetch_july2025.py` |
| Warnings | Real NWS times: FFW 01:14, FF Emergency Hunt 04:04, FF Emergency Hunt→Kerrville 05:36 CDT | `config/regions/hill_country.yaml` |

**Flood model (HAND, "fill the low ground"; overview §6.5).**
- For a river point at chainage *s*: `WSE(s,t) = z_ref(s) + rise(s,t)`.
  - `z_ref` is the low-flow water surface from the DEM (lidar sees the water, not the bed). It is forced to never rise downstream.
  - `rise(s,t)` interpolates linearly between the two bracketing gauges. Each gauge is read with a travel lag `(s − s_g)/c`.
  - The wave speed `c` is fitted from the real peak times: Hunt 05:10 → Kerrville 06:45 gives **c = 2.83 m/s**.
- A road's depth is `max(0, WSE at its nearest river point − road elevation)`.
- A road can't sit below normal flow. Where the DEM says it does, it's a ford, and it starts 0.6 m above normal flow (`sim/region_flood.py:_depths`).

**Truth vs belief.** This separation is the reason drones exist in the model.
- **Truth** is what the water really did:
  - Real gauges, with the Hunt gauge's outages bridged from the downstream gauge's shape. It died at 05:10 CDT after a record 37.52 ft, and the NWS later listed it as destroyed.
  - Ungauged creeks scaled from a similar gauge, labelled *modeled*.
  - Code: `sim/hand_flood.py:fill_gap`.
- **Belief** is what a sensor-only system can know at time *t*:
  - Only readings already reported (`causal=True`): never a future reading, and never a dead gauge.
  - The South Fork, where the camps were, had no reporting gauge that night. Belief there stays at its prior.
- Drones are the only way truth enters belief.

Calibration (`vault/Experiments/2026-11-08 July 2025 replay calibration.md`):
- The model floods its first SH 39 segment in Hunt at 03:15. The real report was "under water by 04:22", which is consistent because that report is an upper bound.
- The first Kerrville roads flood at 04:25, ahead of the 05:45 minor-flood stage. Those are low park and creek roads.

## 2. Belief per crossing: p_flooded (overview §6.3–§6.4)

`fusion/segment_status.py:p_flooded`. All weights live in `config/fusion.yaml`.

```
prior        0.30 floodable and inside a warning   (0.02 otherwise)
+0.15        upstream reporting gauge rising >= 2 ft/hr
+0.15        gauge-interpolated stage is above this road
+0.15        heavy rain (> 1 in/hr; NWS: 4-5 in/hr over the South Fork, 02:00-05:00)
+0.20        Drive Safe & Save stops/U-turns (synthetic)
cap 0.85     indirect evidence alone can never say "confirmed"
override     drone sees water / agency closure -> 0.95; drone sees dry -> 0.10 (never 0: we never say "safe")
decay        a dry snapshot's weight halves every 30 min while gauges rise (2 h otherwise);
             a wet snapshot stays confirmed until new direct evidence
bands        < 0.15 open | < 0.5 unknown | < 0.9 likely | >= 0.9 confirmed
```

## 3. Who depends on which crossing: chokepoints as cuts (overview §7, §8.1–§8.2)

**Areas (nodes).**
- 6,582 synthetic households are placed on real OSM building footprints, with seeded attributes: 30% aged 65+ (Kerr County is one of Texas' oldest counties), 12% manufactured homes, and 85% with the car home at night.
- Camps and RV parks from OSM are separate areas with **generic labels**.
- Each home snaps to the road graph. A super-sink **T** connects to every safe destination: main-road nodes at least 12 m above the nearest waterway, i.e. high ground.

**Definition.** Crossing *c* is **unavoidable** for area *n* if and only if every path n → T uses *c*. Equivalently, *c* is a size-1 edge cut between *n* and *T*: if *c* floods, *n* is cut off.

**Computation** (`critical/access.py:node_access`):
1. **k = 3 exit routes:** run Dijkstra three times, multiplying every used edge by 3 between runs so the routes genuinely differ (overview §8.1).
2. **Candidates:** the floodable points on *all* k routes. Every unavoidable point must lie on every route, so this is a cheap superset.
3. **Exact test:** remove one candidate and ask if *n* can still reach *T* (BFS). This is the colleague's `reachable(blocked=c)` sensitivity test, applied per area.
4. **Optional points:** those on some route but not unavoidable. Losing one costs an option, not the exit.
5. **Areas:** homes sharing the same (unavoidable, optional) signature form one area (overview §7.1).

**Result on the real map:**
- 262 floodable points, of which 98 matter to someone, across 87 areas.
- The largest chokepoints are rural:
  - The SH 39 bridge over Cypress Creek is the only way out for 138 households, including two riverside camps.
  - The FM 1340 bridges on the North Fork carry 73 households each.
  - South Fork crossings on Arrow Head Rd and Flaming Arrow Rd are single exits too.
- A few small Kerrville pockets also depend on a single crossing (6 areas, the largest 13 households). Large Kerrville neighborhoods have alternatives.

**Re-scoring captures sequential cuts.** When a snapshot confirms a crossing flooded, it is removed and the cut tests re-run. A crossing that was optional can become unavoidable. This is overview §8.5's "the next most useful flight may be the back road".

**When an area is cut off**, the system asks whether a high-clearance truck (< 24 in of water) can still reach it from a fire station (`truck_access`).
- If yes, points on that approach get `truck_access` dependency.
- If no, the answer is **boat required**.

## 4. Which crossing first: the priority score (overview §8.4)

`critical/score.py:priority`

```
priority = dependency x vulnerability x (0.5 + p) x 4p(1-p) x urgency
```

| Factor | Meaning | Why |
|---|---|---|
| dependency | Σ households × (1.0 unavoidable, 0.3 optional, 0.5 truck access) | Stakes: how many people's instruction depends on this answer. The colleague's "1000 × areas that lose all exits" heuristic is the same idea, scored continuously |
| vulnerability | 1 + 0.5 older + 0.3 one-story/manufactured + 0.3 cars still home, household-weighted | Who can't easily self-rescue or go upstairs. It orders outreach, **never pricing** |
| 4p(1−p) | Bernoulli variance scaled to [0, 1] | **Value of information.** 1 at p = 0.5, 0 when we already know. A crossing confirmed by a sensor or closure scores 0, so we never waste a flight on it. It is binary entropy without the logs: same maximum, same zeros |
| 0.5 + p | Lean toward probably-flooded | See below |
| urgency | 1.5 if the gauge-only forecast puts water on the road within the next hour | Information about a crossing that's about to flood decays fastest |

**Why the peak is at p ≈ 0.61, not 0.5.**
- Let `f(p) = (0.5+p)·p(1−p) = 0.5p + 0.5p² − p³`.
- Then `f′(p) = 0.5 + p − 3p² = 0`, so **p\* = (1+√7)/6 ≈ 0.608**.
- The bias encodes an asymmetric loss. Missing a flooded crossing (someone drives into water) is worse than missing a dry one (someone takes a detour).
- Tested in `tests/test_critical_score.py::test_value_peaks_on_the_likely_flooded_side`.

**Worked example (overview §8.7).**
- X1 is a sensorless low-water crossing serving a village (40 households) and a farm (1), p = 0.5. Priority = 41 × 1 × 1.0 × 1.0 = 41.
- X2 is optional for a subdivision (25), p = 0.6. Priority = 7.5 × 1.1 × 0.96 = 7.9.
- X3 is a sensor bridge, p = 0.95. Priority = 7.5 × 1.45 × 0.19 = 2.1.
- The drone goes to X1 first (`test_worked_example_ranks_x1_first_and_sensor_point_last`).

## 5. Where each drone flies: the trajectory planner

`drone/planner.py:plan`

**Problem.** Visit a subset of critical points with a few drones, each with a battery, to maximize information value. This is a **team orienteering problem with time-decaying rewards**, which is NP-hard. At our size (≤ 20 live candidates, 3 drones) the following is near-optimal and fast.

**Reward for reaching point i at time t:**
```
V_i(t) = priority_i · exp(−max(0, t − deadline_i) / τ),   τ = 20 min
```
- The deadline is now + 15 min for urgent points, and now otherwise.
- Late information is worth less: people behind the crossing must decide.

**Constraint:**
```
flight + hover(15 s, +25 s waterline hold if urgent) + return to the nearest station  <=  battery × (1 − 20 % reserve)
```

**Leg time (terrain-following).**
- The drone holds a constant 80 m above ground, under the FAA Part 107 limit of 400 ft AGL.
- Leg time = horizontal distance / 15 m/s + Σ climbs / 4 m/s, sampled every 60 m on the DEM.
- Flying at "the highest ridge + clearance" instead would put it well over 120 m above Hill Country valley floors.

**Algorithm.**
1. **Greedy ratio insertion:** repeatedly add the (point, drone, position) with the best *added value per added second*, among those that keep the tour battery-feasible. Every drone competes for every point, so no point is assigned twice.
2. **2-opt:** reverse sub-tours while value rises, or while time falls at equal value.
3. **Rolling horizon:** fly only the first leg. After each snapshot, the evidence changes p, which changes the cuts, which changes every priority. Re-plan (overview §8.5).

**Dispatch rules.**
- No flights before a warning.
- Never fly to an "open" point (p < 0.15), because the answer wouldn't change an instruction. The exception is a point on a cut-off area's high-clearance truck approach.
- A point re-enters the queue only after its snapshot decays (overview §8.6).

## 6. What each area is told, and its risk score: move people from low to high ground

**Area risk** (`critical/area_risk.py`). Every area has a 0–100 score, and each factor's contribution is returned:
```
risk = 35·access + 25·water + 25·ground + 15·vulnerability
  access  cut_off 1 | at_risk 0.7 | partially_cut_off 0.4 | ok 0
  water   max p_flooded over its exits (1 if its own roads have water)
  ground  1 − height_above_nearest_waterway / 15 m
```
- Bands: low < 25 ≤ moderate < 50 ≤ high < 75 ≤ severe.
- Ground labels: low < 5 m ≤ mid < 12 m ≤ high.
- `/api/region/nodes` is sorted highest risk first. This is the order in which to move people.

**Instructions** (overview §10.1, `critical/loop.py:_node_update`):

| Situation | Instruction |
|---|---|
| All exits confirmed flooded | **Shelter in place**, go to the highest floor or high ground, responders flagged with truck route or boat required |
| All exits likely (not confirmed) | **Wait for check**: a drone is tasked. Never shelter people on a guess |
| The only exit crosses an unknown crossing | **Wait for check**: "Do not drive through any water" |
| Some exits flooded, one open | **Route out to high ground** |
| Exits not at risk | No message (avoid alert fatigue) |

**Route out** (overview §10.2, `routing/instructions.py`).
- Edge cost is length × (open ×1, unknown ×3, likely ×50). Confirmed flooded edges are removed.
- The route always ends at a high-ground destination (at least 12 m above the nearest waterway).
- The message never says a road is safe. It says "this route avoids known flooding" and always ends with the turn-around rule.

## 7. Results on the July 4, 2025 replay

From `uv run python -m scripts.replay_report` (2026-11-08, after review fixes). Results are recorded in `vault/Experiments/2026-11-08 July 2025 replay calibration.md`.

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


## 8. Limits we state openly

- **Heuristic probabilities:** these are not calibrated against labelled events.
- **Single cuts only:** joint cuts appear only through sequential re-scoring.
- **Not hydraulics:** HAND, with no velocity, backwater dynamics or debris.
- **Synthetic people and snapshots:** households are synthetic, and snapshots are generated from the replay truth.
- **No FEMA zones:** the NFHL is not cached, so FEMA flood zones are absent from the floodable filter.
- **Simulated fleet:** the planner assumes free airspace and three drones at real fire stations. Real operations need FAA waivers for beyond-visual-line-of-sight flight at night.
