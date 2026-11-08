---
tags: [hitide, module]
status: done
updated: 2026-11-08
---

# Risk Surface

A continuous Flood Risk Index (0 to 100) over the Hunt to Kerrville study area, one grid per 30 minutes of the July 4, 2025 replay. The ops map draws it as a heat surface. It is a **relative index**, not a water depth, a probability, or a FEMA zone.

Code: `backend/scoring/risk_grid.py` (pure numpy, TDD: `backend/tests/test_risk_grid.py`, 19 tests), build `backend/scripts/build_risk_grid.py`, tunables `backend/config/risk_grid.yaml`.

```
cd backend && uv run python -m scripts.build_risk_grid
```

Runs offline in about 4 s.

## Inputs

- Terrain: `data/region/hill_country/dem30.npz` (USGS 3DEP 10 m, 3x3 max-pooled to 30 m). 2x2 blocks give a 647 x 306 grid of about 58 m cells, labelled 60 m.
- Waterways: `waterways.geojson`. Every line is rasterized as a stream cell. Named rivers carry a bed profile from the 10 m DEM (non-increasing downstream), and that profile is the reference surface. Unprofiled streams use the lowest DEM cell.
- Rain: cached MRMS 1 h and 24 h tiles (`data/wx/mrms`, z10). The raw IEM tiles need IEM's legend strip to decode, and that strip is fetched online, so the script inverts the recolored NWS ramp instead. Each bin maps to its midpoint, and the open 6 in+ bin maps to 7 in. Each frame uses the newest completed MRMS hour at or before its time (the same rule as the replay rain layer), so the :30 frames repeat the :00 rain.

## Formula

```
hand    = clip(1 - HAND / 15 m, 0, 1)      HAND = lowest ground in cell - nearest waterway bed
dist    = exp(-distance / 400 m)
rain1h  = clip(in / 3, 0, 1)    rain24h = clip(in / 10, 0, 1)
terrain = 0.6 hand + 0.4 dist
rain    = 0.6 rain1h + 0.4 rain24h
index   = 100 * terrain * (0.15 + 0.85 * rain)
```

Rain multiplies terrain susceptibility. A dry ridge stays near 0 in any rain, and a dry river corridor tops out at 15. Top factors rank the group-weighted contributions [hand, dist, rain1h, rain24h] (indices 0 to 3).

## Outputs (`frontend/public/grids/`)

- `index.json`: bounds, width, height, cell_m, factor labels, frames (id in local CDT, time in UTC, kind observed/forecast, url, factors_url, min, max).
- `{id}.bin`: Float32 LE, row-major with row 0 at north, NaN outside the DEM.
- `{id}.factors.bin`: Uint8 `(top << 4) | second`, 255 where NaN.
- `study_area.geojson`: convex hull of valid cells.
- 14 observed frames (01:00 to 07:30 CDT) plus 2 forecast frames (08:00, 08:30). Total 15.8 MB.

## Result on July 4, 2025

The peak is 89.8 at 03:00 to 04:30 CDT, when the Hunt cell dumped more than 3 in/h. The 01:00 maximum is 40.5. The index eases to 45 to 49 after 06:00 as the hourly rain moves off, but the 24 h totals keep the corridors elevated. Kerrville's river cells rise steadily (23.5 at 01:00, 34.1 at 07:30) because Kerrville got less rain than Hunt. The highest ridge (682 m) stays at 0.2 to 0.3.

## Limits

- Relative index only. It has no hydraulics and no upstream-flow or gauge term, so it does not show the river cresting at Kerrville after the rain stops. The depth frames ([[Flood Simulation]]) and gauges do that.
- No FEMA flood zones, because NFHL is not cached offline.
- The study area is the Hunt to Kerrville DEM box, not all of Kerr County.
- Forecast frames are persistence: the 1 h rain decays by x0.8 per 30 min and the 24 h total is held. They never read later archived hours.
- Rain is binned (decoded from the recolored ramp), and the 30 m DEM is max-pooled. Using the lowest 30 m cell per 60 m cell offsets most of that upward bias.
- Bounds use the dem30 `x0`/`y0` as the left and top edges, per the contract. The true edge is about 5 m further out (x0 is the first 10 m cell centre).
