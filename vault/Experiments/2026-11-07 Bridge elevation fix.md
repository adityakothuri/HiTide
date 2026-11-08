---
date: 2026-11-07
tags: [hitide, experiment, flood, bug]
changed: backend/sim/town.py _fix_bridges; scripts/gen_drivers.py demo-d depth window; stages/runner.py recommendation rule
result: Demo depths are now believable (B's crossing 20 in, Margaret's car 21 in), and the recommendation is "boat required"
---

# Bridge elevation fix

Related: [[Flood Simulation]], [[Drone Vision]], [[2026-11-07 Flood calibration]]

**Symptom:** the demo's stalled car sat in 199 in (16 ft) of water while vision said "water at the windows". The recommendation came out as "truck route available".

**Cause:** each road's elevation is the *minimum* DEM sample along the edge. A bridge picks up the **riverbed** under it. 8 of the 40 closed segments at minute 35 were bridges (49 bridges in town).

**Fix:**
1. A bridge takes the highest elevation of its adjacent approach roads (`_fix_bridges`).
2. Demo driver D stalls on a segment 12–30 in deep (doors to windows), not a river crossing.
3. Recommendation: `max(model depth, drone-observed level)` against the 24 in boat threshold, then a truck-route check. Observed levels (sedan, approx.): wheels 12, doors 20, windows 30, roof 50 in.

| | before | after |
|---|---|---|
| closed at 35 min | 40 | 32 |
| closed at crest | 240 | 230 |
| B hazard depth | 197.6 in | 20.1 in |
| D depth | 199 in | 21.2 in |
| recommendation | truck route available | boat required |
