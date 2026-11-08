---
tags: [hitide, experiment, data]
status: done
updated: 2026-11-07
---

# 2026-11-07: Town cache build

Goal: build the offline Kerrville road network and river so the demo runs without network access. Script: `backend/scripts/build_town_cache.py`.

## Run 1: partial failure

- Fetched the drive network from Overpass: **1649 nodes, 4234 edges**.
- The river query failed: **Overpass connection refused**.
- The first run had no mirror fallback and saved nothing after the graph fetch, so the network fetch was lost on failure.

> [!warning] What broke
> One Overpass endpoint is a single point of failure. A failed river query also threw away the completed network fetch.

## Fix

1. **Mirrors**: `OVERPASS_MIRRORS` tries `overpass-api.de`, `overpass.kumi.systems`, and `overpass.private.coffee` in order (`with_mirrors`).
2. **Incremental save**: each stage writes its output to `data/town/` as soon as it finishes. A rerun loads the cached graph (`fetch_graph`).
3. **Fallback line**: if every mirror fails, the river uses the hand-traced `RIVER_FALLBACK` centerline. See [[Decisions]].

## Outputs

- `data/town/graph.graphml`
- `data/town/segments.geojson`: one feature per directed edge with `edge_id`, `u`, `v`, `length_m`, `name`, `elev_m`
- `data/town/river.geojson`

## Notes

- The script's `DIST_M` is 4500 m. The plan said about 6 km. Keep 4500 unless the town needs more area, and record any change here.
- At check time (2026-11-07) the Overpass status endpoint did not respond from this machine. The cache is what makes the demo offline.

## Related

- [[Flood Simulation]]
- [[Data Sources]]
- [[Architecture]]
