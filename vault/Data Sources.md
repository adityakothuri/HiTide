---
tags: [floodwatch, reference, data]
status: in-progress
updated: 2026-11-07
---

# Data Sources

Each source, its auth, and what we use it for. Checked 2026-11-07 unless noted.

| Source | URL | Auth | Use |
|---|---|---|---|
| OpenStreetMap via osmnx (Overpass API) | https://overpass-api.de/api (mirrors: https://overpass.kumi.systems/api, https://overpass.private.coffee/api) | None. Send a User-Agent. Rate limited. | Drive network and Guadalupe River waterway for the town cache |
| USGS 3DEP via py3dep | https://www.usgs.gov/3d-elevation-program (library: https://github.com/hyriver/py3dep) | None | Elevation sampled along each edge to get road elevation |
| NWS alerts | https://api.weather.gov/alerts/active?point=30.047,-99.140 | None. NWS requires a User-Agent header. | Active flood watches and warnings for Kerrville |
| USGS Water Data OGC API | https://api.waterdata.usgs.gov/ogcapi/v1/ (example: `collections/continuous/items?monitoring_location_id=USGS-08166200`) | None | Guadalupe River at Kerrville, gage 08166200, parameter 00065 (gage height) |
| USGS Real-Time Flood Impacts (RTFI) | https://api.waterdata.usgs.gov/rtfi-api/referencepoints/nwis/08166200 (docs: https://api.waterdata.usgs.gov/rtfi-api/docs) | None | 5 impact reference points on gage 08166200 with flood stages of 7, 13, 13, 13 and 26 ft (riverbank, resort, restaurant, park lot). Verified live 2026-11-07. |
| Photon Spectrum | https://spectrum.photon.codes (OpenAPI: https://spectrum.photon.codes/openapi/json) | Basic auth: `SPECTRUM_PROJECT_ID` and `SPECTRUM_PROJECT_SECRET` | Texts, polls, read receipts, outbound SIP voice on the iMessage line |
| ElevenLabs Conversational AI | https://elevenlabs.io/docs | API key: `ELEVENLABS_API_KEY` | Outbound voice call to the driver through a SIP trunk |
| NWS "Turn Around Don't Drown" | https://www.weather.gov/safety/flood-turn-around-dont-drown | None | Depth thresholds for road status ([[Risk Scoring]]) |
| Public drone flood images | Sources recorded per image in `data/drone_samples/sources.md` | Per source license | Drone vision batch ([[Drone Vision]]) |
| USGS July 3–5, 2025 gage height (5 sites: 08165300, 08165500, 08166000, 08166140, 08166200) | https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items?monitoring_location_id=USGS-08166200&parameter_code=00065&datetime=2025-07-03T00:00:00Z/2025-07-06T00:00:00Z | None | Hill Country replay. Peaks: Hunt 37.52 ft at 05:10 CDT (record, then silent about 34 h), Kerrville 37.51 ft at 06:45, N Fork 21.2 ft at 05:30. Cached in `data/region/hill_country/hydrographs_2025-07-04.json` |
| NWS EWX July 2025 hydrology report (E-5) | https://www.weather.gov/media/ewx/Hydro/MonthlyReports/E-5%20EWX%202025-07.pdf | None | Kerrville crest 37.48 ft at 6:45 am; Hunt gauge destroyed |
| KSAT flood timeline (2025-08-03) | https://www.ksat.com/news/local/2025/08/03/flood-timeline-alerts-emergency-response-and-pivotal-moments-in-july-4-tragedy-in-the-hill-country | None | FFW 1:14, FF Emergency Hunt 4:04, Hunt→Kerrville 5:36, SH 39 in Hunt under water about 4:22 |
| KXAN on the NWS report | https://www.kxan.com/independence-day-floods/national-weather-service-releases-new-report-on-deadly-central-texas-floods/amp/ | None | 7–12 in over the South Fork in about 3 h, peak 4–5 in/hr (heavy-rain window) |
| Kerr County deaths | https://ksat.com/news/local/2025/08/04/one-month-later-maps-graphics-show-the-severity-of-the-hill-country-floods | None | 108 as of Aug 4, 2025. Sources differ by date, so always say the date |
| OSM places + buildings (Hill Country bbox) | Overpass via osmnx | None | Fire stations (drone bases), hospitals/schools, camps/RV parks (generic labels on screen), 7,586 building footprints → 6,582 synthetic households |
| Texas Dept. of Insurance Hurricane Harvey data call | https://www.insurancejournal.com/news/southcentral/2018/02/13/480405.htm | None | Average paid auto loss **$19,943** (about 203,000 Texas auto claims, data through late Oct 2017). Feeds `claims.avg_vehicle_claim_usd`. Earlier CCC data put Harvey's average at about $14,900 with 80-85% total losses. |

> [!note] Overpass was flaky
> On 2026-11-07, the first build got the road graph, then `overpass-api.de` refused the river query. The second run (with a mirror fallback and incremental saves) got the real OSM river. The cache is committed so the demo never depends on Overpass. See [[2026-11-07 Town cache build]].

> [!note] USGS Flood Impacts
> Verified live on 2026-11-07. The impact points describe nearby road and bridge flooding, but none is itself a road segment, so the ops panel shows them as context only. USGS gage values arrive as strings and are converted to floats.

## Feed rules

- Every feed has a 5 s timeout and falls back to `data/feeds_cache/`.
- Responses carry `source: live` or `source: cached`.
- The demo runs fully offline from cache.

## Code

- `backend/scripts/build_town_cache.py` (exists): OSM, 3DEP, river
- `backend/feeds/base.py`, `nws.py`, `usgs_ogc.py`, `usgs_flood_impacts.py` (exist)
- `data/feeds_cache/` (exists): cached feed responses, refreshed by live calls

## Related

- [[Architecture]]
- [[Flood Simulation]]
- [[Photon Outreach]]
