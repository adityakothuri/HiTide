---
date: 2026-11-07
tags: [hitide, experiment, flood]
changed: config/weights.yaml flood block
result: ~6% of road segments closed at crest, concentrated along the Guadalupe
---

# Flood calibration

Related: [[Flood Simulation]], [[2026-11-07 Town cache build]]

**Data:** 4234 directed road segments. Real OSM river. USGS 3DEP 10 m DEM, range 476-617 m. 5th percentile elevation of segments within 100 m of the river: 480.1 m.

**Sweep** (closed-or-worse segment count at crest):

| decay m/km | rise 4 m | rise 7 m | rise 10 m |
|---|---|---|---|
| 3 | 10 | 40 | 130 |
| 5 | 8 | 38 | 112 |
| 8 | 8 | 38 | 102 |

Kerrville roads mostly sit well above the river, so decay barely matters. Rise height is what drives the result.

**Chosen:** base WSE 478 m, rise 0.2 m per sim minute, max 13 m, decay 3 m/km, reach 1.5 km.

| sim min | caution+ | closed+ | boat |
|---|---|---|---|
| 10 | 6 | 4 | 4 |
| 30 | 36 | 36 | 30 |
| 50 | 134 | 130 | 118 |
| 65 | 246 | 240 | 222 |

The demo drivers are generated against the flood state at 35 sim minutes (40 closed segments). See `backend/scripts/gen_drivers.py` `DEMO_FLOOD_MIN`.

**Live check:** at 60x, 40 real seconds produced 29 `segments.update` events and the river rose 7.8 m (expected: 39 min × 0.2 m/min).
