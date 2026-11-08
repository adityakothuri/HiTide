---
tags: [floodwatch, module, sim]
status: in-progress
updated: 2026-11-07
---

# Flood Simulation

Computes how deep water is over each road segment as the Guadalupe River rises, then moves drivers along their routes.

## Model

- River water surface `wse(t)` rises along the Guadalupe (`flood.rise_m_per_min`, capped at `flood.max_rise_m`).
- WSE drops with distance from the river centerline (`flood.decay_m_per_km`). Beyond `flood.reach_km`, no flooding.
- Depth per segment: `depth_in = max(0, wse_at(segment) - road_elev)`, converted to inches.
- Pure functions, vectorised with numpy.

## Town data

The offline cache is built once by `scripts/build_town_cache.py` (see [[2026-11-07 Town cache build]]).

- OSM drive network (osmnx, Overpass mirrors), simplified
- Road elevation per segment: minimum along each edge, sampled from USGS 3DEP (py3dep)
- Guadalupe River centerline from an OSM waterway, with a hand-traced fallback

Current outputs in `data/town/`: `graph.graphml`, `segments.geojson`, `river.geojson`.

> [!note] File names differ from the plan
> The plan named `kerrville_graph.graphml` and `segments.parquet`. The build script writes GeoJSON and GraphML, so the code and this note follow the script. Update the plan if the team wants parquet.

## Code

- `backend/scripts/build_town_cache.py` (exists): builds `data/town/`
- `backend/sim/town.py` (exists): loads the cached graph and segments
- `backend/sim/flood.py` (exists): `wse(t)` and depth per segment
- `backend/sim/drivers.py` (exists): 2-3 usual routes per driver
- `backend/scripts/gen_drivers.py` (exists): seeded generator for the synthetic drivers
- `backend/sim/movement.py` (planned): advances drivers each tick
- `backend/sim/engine.py` (exists): tick loop and clock
- `backend/tests/test_flood.py` (exists): flood depth tests (not in the TDD list, so keep them light)
- `backend/config/weights.yaml` (exists): `flood` block
- `data/town/` (exists): cached graph, segments, river

## Related

- [[Risk Scoring]] reads depth from this module
- [[Data Sources]] for OSM, 3DEP, and the gage feed
- [[Architecture]]
