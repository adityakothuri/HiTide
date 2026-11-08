# Real flood footage used for the drone vision demo

Raw video (`raw/`) and renders (`out/`) are gitignored. Anything not marked public domain is **copyrighted. It is used only for an internal hackathon demo and is credited on screen.** Don't publish or redistribute it without the owner's permission.

| Render | Source | Owner / licence | When | Where | Elevation shown |
|---|---|---|---|---|---|
| `1_riverside_dr_car_flood.mp4` (technical style) | [YouTube 9_YRjLamWRU](https://www.youtube.com/watch?v=9_YRjLamWRU), KSAT "Houses along Guadalupe River near Kerrville under water" | KSAT 12, Alex Gamez, © | July 4, 2025. The live ticker reads 7:31 AM; window 7:15–7:31 CDT | Riverside Dr bridge near Kerrville | Gauge USGS 08166200 (upstream). The key's CI95 and P(±1 ft) treat the capture time as uniform over the window |
| `2_ingram_truck_submerged.mp4` (technical style) | [YouTube 5ZaNf7ay4CQ](https://www.youtube.com/watch?v=5ZaNf7ay4CQ), KHOU "Texas flash flooding leaves vehicle partially submerged in Ingram" | KHOU 11, Krystin Ward, © | **July 16, 2026 (a later flood, not July 4, 2025)**, at night. Window 01:00–06:30 CDT | Ingram, TX | Gauge USGS 08166140, about 4 km downstream (`usgs_2026-07_ingram.json`, provisional). The long window gives P(±1 ft) 0.11, which is honest and low |
| `3_dietert_river_trail_model.mp4` (technical style) | Same as `A_` below | | | | **Model**, with CI95 and P(±1 ft) from a Monte Carlo over the camera-pose uncertainty plus lidar error |
| `A_dietert_river_trail.mp4` | [YouTube tFCaJNsK3_8](https://www.youtube.com/watch?v=tFCaJNsK3_8), "Kerrville, Guadalupe River - Flooding - July 4th, 2025" | Travis Humphreys, © | July 4, 2025. Debris on the fence shows the falling limb; the gauge cross-check gives about 8:2x AM CDT | Filmed from the Dietert Center over the River Trail, at the filmer's published coordinates 30°03'02.2"N 99°09'26.4"W, looking south | **Model** (georeferenced: 1 m 3DEP lidar plus a camera fit to the River Trail edges), with a gauge cross-check |
| `B_kerrville_bridge_crest.mp4` | [The Independent](https://www.independent.co.uk/tv/news/video-kerrville-texas-deadly-rain-flood-bridge-b2783000.html), "Deadly flooding in Texas captured from bridge" | City of Kerrville via The Independent, © | July 4, 2025. Window 6:30–7:30 AM CDT, inferred from dawn light near the 6:45 AM crest | A Kerrville bridge over the Guadalupe | Gauge only |
| `D_nimitz_dam_556am.mp4` | [YouTube AKqUeHKqwr4](https://www.youtube.com/watch?v=AKqUeHKqwr4), WOAI "Guadalupe River flooding in Kerrville" | Chris Dean via News 4 San Antonio (WOAI), © | **5:56 AM CDT, July 4** (timestamp on the clip) | Below Nimitz Lake Dam, from Guadalupe Street | Gauge only |
| `C_coast_guard_aerial_jul6.mp4` | [DVIDS 970125](https://www.dvidshub.net/video/970125/coast-guard-aircrew-conducts-overflight-flooded-areas-texas-hill-country) | U.S. Coast Guard, PO3 Perry Shirzad. **Public domain** | July 6, 2025 | Hill Country overflight from Kerrville airport | None. Aircraft pose isn't published |

Also downloaded but not rendered: DVIDS 970698 (Texas Army National Guard CH-47, July 16, public domain, aftermath) and news compilations from KSAT, NBC DFW, NY Post and the Statesman, which have broadcast overlays.

## Gauge

USGS 08166200, Guadalupe River at Kerrville. The datum is **1601.14 ft NAVD88** (USGS site inventory), the same vertical datum as 3DEP lidar. Stage comes from `data/region/hill_country/hydrographs_2025-07-04.json`, the USGS Water Data OGC API, approved data. The crest was 37.51 ft at 6:45 AM CDT.

## Site data (`dietert/`)

- `dem1m.npz`: USGS 3DEP 1 m lidar (2018, EPSG:5070) via `py3dep`.
- `osm.geojson`: OpenStreetMap features, including the River Trail.
- `site.json`: the camera prior, pixel picks along both River Trail edges at t = 50 s, and the pose priors.
