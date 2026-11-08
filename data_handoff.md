# Texas data integration handoff

Updated November 7, 2026. This file summarizes the implemented collectors for another agent taking over the work. Texas is the operational scope. Kerrville is a bounded simulation and offline test case.

Detailed schema proposals, attribution, response examples and unresolved normalization questions are in [MAP_DATA_ACCESS.md](docs/MAP_DATA_ACCESS.md). The frontend contract is in [api-contract.md](docs/api-contract.md).

## Entry points

- Open the statewide monitor at `/texas` or the home page. The local test console is at `/console`.
- `GET /api/feeds/recent?scope=texas&max_age_minutes=30` returns source batches and full intake records. Supported freshness windows are 15–30 minutes.
- Add `map_view=true` for the frontend response. It omits unused raw fields and simplifies construction geometry to 0.002 degrees. Use full geometry for subsequent spatial analysis.
- `await feeds.collect_raw(scope="texas")` collects statewide raw envelopes. It performs no database writes.
- `await feeds.collect_raw(scope="kerrville", cache_only=True)` replays the local fixtures. These fixtures retain their original location and age.
- `python -m scripts.demo_flood_monitor --live`, run from `backend/`, evaluates Texas NWS warnings using the temporary in-memory detector. Without `--live`, it replays a historical Florida warning.

## Refresh and time rules

The frontend polls once per minute. Each backend process shares a snapshot for up to 60 seconds and reevaluates freshness on every read. DriveTexas additionally limits its own network polling to once every five minutes.

Near-live admission requires live provenance and an interpretable provider timestamp inside the selected window. Cached, future-dated, stale and unknown-time records receive explicit exclusion reasons. Retrieval time cannot replace an observation time. An old closure or warning may remain in force after it disappears from a recent-updates view. An empty result cannot establish that a road reopened.

Each source batch has `status`, `records`, `context`, `excluded`, `errors`, and optional `label` and `notes`. Status is complete, partial or unavailable and describes retrieval coverage. A complete response can contain zero recent observations. Timestamp-unverified context requires an explicit checkbox in the UI.

## Connected source inventory

Counts below describe verification snapshots, before freshness filtering where stated. They are useful regression references and will change.

| Source ID | Coverage and data | Time, units and interpretation | Implementation |
|---|---|---|---|
| `nws_alerts` | Active Texas watches, warnings and advisories using `area=TX`. Six messages returned in an initial check. | `properties.id` is CAP identity. Preserve `sent`, `effective`, `expires`, status, message type, references and affected zones. Recent flood messages must have a recent issue time and a current validity interval. Geometry can be null. | [texas.py](backend/feeds/texas.py) |
| `usgs_gage` | Latest Texas gage-height measurements using state FIPS 48 and parameter 00065. Queries a rolling hour and follows cursor pages. | Preserve feature ID, station ID, series ID, sample `time`, modification time, original value string, units, approval status, method and qualifiers. Gage height is station-relative. Its datum requires station metadata before terrain comparison. | [texas.py](backend/feeds/texas.py) |
| `nws_local_storm_reports` | Texas NWS reports distributed by Iowa Environmental Mesonet. Requests the last 30 minutes with `states=TX`. Selects flood reports mentioning a road. | `valid` is observation time in UTC. Preserve issuing office, reporter role, remarks and product ID. The response feature index is not durable observation identity. Depth may appear in prose, such as a reported 6–8 inches. The collector preserves the text without inventing a numeric depth or closure status. | [texas_roads.py](backend/feeds/texas_roads.py) |
| `drivetexas_work_zones` | State-maintained Texas highways. WZDx construction feed returned 2,264 records, with 809 inside their scheduled intervals during one check. | Preserve feature ID, road names, vehicle impact, description, direction, schedule, verification flags and individual edit date. Freshness uses feed publication time plus the active interval. Publication does not establish a new field observation. Geometry is a road line. | [drivetexas.py](backend/feeds/drivetexas.py) |
| `noaa_mrms` | NOAA radar rainfall-rate grid. Decodes 266 coarse Texas area summaries from timestamped GRIB2 files. | Original GRIB units are [mm/hr]. Preview value is the spatial maximum of nonnegative pixels in a 0.5-degree cell. Geometry marks its center. Edge windows can include neighboring states. Preserve product valid time, original CRS, GRIB time tags and immutable raw-file reference. | [noaa_products.py](backend/feeds/noaa_products.py) |
| `noaa_flash` | NOAA modeled maximum unit streamflow guidance, decoded into 266 coarse Texas area summaries. | Original units are [m^3/s/km^2]. Both temporal forecast maximum and spatial preview maximum apply. Product valid time is separate from model reference time. Forecast horizon is unresolved and version-dependent. No road-depth interpretation is implemented. | [noaa_products.py](backend/feeds/noaa_products.py) |
| `noaa_nwps` | NOAA river observation and forecast summaries. Queries a Texas bounding box, then filters state abbreviation to TX. Returned 723 Texas summaries. | Preview uses observed `validTime`, primary value/unit and flood category. Preserve station LID, PEDTS and forecast fields. Datum and measurement meaning require metadata. Some observations duplicate underlying USGS evidence. | [noaa_products.py](backend/feeds/noaa_products.py) |
| `lcra_hydromet` | Lower Colorado basin and partner stations. Returned 406 station records with rainfall and stage. | UTC `dateTime`; one-hour rainfall in inches and stage in feet. Vertical reference is unverified. Preserve site number, agency, all accumulation windows and originals. Most stations report about every 15 minutes, with some hourly. Data is provisional. | [local_sensors.py](backend/feeds/local_sensors.py) |
| `hcfcd_water_levels` | Harris County Flood Warning System. The HCFCD region query returned 204 station features. | Preview selects the latest interpretable stream reading. Site wall times are interpreted as America/Chicago, rejecting ambiguous/nonexistent DST instants. Coordinates arrive as strings. Preserve all sibling sensors, channel metadata and flags. Level units are feet, with vertical reference unresolved. | [local_sensors.py](backend/feeds/local_sensors.py) |
| `hcfcd_inundation` | Harris County modeled inundation-layer availability. Checks current and preceding half-hour layers. A real WebP tile also responded during verification. | Uses the actual available layer time. The integration exposes availability and the county viewer. Raster georeferencing, depth-band decoding and road intersections remain unfinished. An empty/transparent tile cannot establish dry roads. | [local_sensors.py](backend/feeds/local_sensors.py) |
| `atx_flood_closures` | ATXFloods participating jurisdictions through City of Austin GIS. The live query returned an empty collection. | Preserve provider IDs, status, name/address, jurisdiction, comments and point geometry. The declared schema has no observation timestamp. Nonempty records are currently context only. A transfer-limit flag produces an incomplete-response marker. | [regional_roads.py](backend/feeds/regional_roads.py) |
| `sariver_crossings` | Monitored crossings in the San Antonio basin network, including Bexar, Wilson, Karnes and Goliad counties. Returned 200 sensor records. | Verified status IDs are 1 Closed, 2 Open, 3 Inactive and 4 Caution. Preserve asset/agency IDs and original dates. Dates omit timezone offsets, so the preview leaves freshness unknown and offers the status as optional context. | [regional_roads.py](backend/feeds/regional_roads.py) |
| `txdot_cameras` | Statewide camera inventory with 4,366 returned locations. | No capture timestamps or fresh images were verified. All `isActive` flags were false in the inspected catalog, with semantics unresolved. Owner is not a unique camera ID. Preserve name/coordinates as identity hints. Context only, without automated water detection. | [local_sensors.py](backend/feeds/local_sensors.py) |
| `transtar_incidents`, `transtar_lane_closures`, `transtar_flood_risk` | Houston TranStar documents live JSON feeds. Incident and closure status feeds are documented as updating once per minute. | Live access requires contacting TranStar. Adapters emit `live_feed_access_required`. Public samples are historical and excluded. Roadway flood-risk areas represent inference, with actual closure/depth requiring separate evidence. | [regional_roads.py](backend/feeds/regional_roads.py) |

## Endpoint reference

Public URLs below contain no credentials. Check the linked code for exact request parameters.

| Provider/product | Endpoint |
|---|---|
| NWS active Texas alerts | [Active alerts](https://api.weather.gov/alerts/active?area=TX) |
| USGS latest gage heights | [Latest continuous collection](https://api.waterdata.usgs.gov/ogcapi/v1/collections/latest-continuous/items) |
| NWS reports via IEM | [Local Storm Reports GeoJSON](https://mesonet.agron.iastate.edu/geojson/lsr.geojson) |
| DriveTexas construction | [WZDx endpoint](https://api.drivetexas.org/api/conditions.wzdx.geojson) |
| NOAA rainfall | [MRMS PrecipRate catalog](https://mrms.ncep.noaa.gov/2D/PrecipRate/) |
| NOAA runoff | [FLASH grid catalog](https://mrms.ncep.noaa.gov/2D/FLASH/CREST_MAXUNITSTREAMFLOW/) |
| NOAA river summaries | [NWPS gauges](https://api.water.noaa.gov/nwps/v1/gauges) |
| LCRA | [Station JSON](https://hydromet.lcra.org/api/GetDataForAllSites) |
| Harris County levels | [Station data](https://www.harriscountyfws.org/Home/GetSiteRecentData?regionId=1&timeSpan=2) |
| Harris inundation | Layer existence uses `https://inundation.hcfcd.org/api/Layer/Exists/{YYYYMMDDHHmm}`. Tiles use `https://inundation.hcfcd.org/api/Tiles/{layer}/{quadkey}`. |
| Austin flood closures | [GIS query](https://maps.austintexas.gov/gis/rest/PublicSafetySharedServices/SharedAtxFloodRoadClosure/MapServer/0/query) |
| San Antonio basin crossings | [Sensor API](https://api.bexarflood.org/api/sensors/GetAll) and [status definitions](https://api.bexarflood.org/api/Meta/GetAllSensorStatusTypes) |
| TxDOT camera inventory | [Catalog](https://its.txdot.gov/its/Map/GetIconModelsOfType?type=camera) |
| TranStar access | [Feed documentation and contact](https://traffic.houstontranstar.org/api/api_doc.aspx) |

## Supporting map and test data

- `usgs_flood_impacts` supplies Kerrville reference thresholds and impact descriptions. It lacks a measurement instant, so its displayed gage snapshot is excluded from near-live observations. Thresholds become useful after a verified join to timed, datum-compatible stage evidence.
- The local builder uses OpenStreetMap/Overpass for roads and river geometry and USGS 3DEP for terrain. These are versioned map context. Bare-earth DEM values may differ from bridge-deck elevations.
- The statewide outline comes from Census TIGERweb and is saved in [texasBoundary.json](frontend/src/evidence/texasBoundary.json). The raster previews use that outline for cell-center selection.
- Sanitized response examples are in [docs/examples/map-data](docs/examples/map-data). They include historical and empty responses. Preserve their original time and geography during tests.
- Attribute NWS/NOAA, USGS, Iowa Environmental Mesonet, TxDOT, LCRA, HCFCD, City of Austin, San Antonio River Authority and contributing agencies as applicable. OSM requires contributor attribution and ODbL handling. Preserve provider license metadata and review product-specific access/redistribution terms before deployment.

## Intake and implementation boundary

[RawEnvelope](backend/feeds/intake.py) carries source ID, optional provider record ID, attempt ID, record position, current retrieval time, original payload retrieval time, sanitized parameters/scope, provider metadata, raw payload or reference, provenance, status and error codes. A successful empty request and a failed request remain distinct.

The future normalizer receives envelopes through `IntakeConsumer.receive(envelope)`. Collection, temporary display interpretation and database writes are separate. Expanded previews are dispatched by [source_views.py](backend/feeds/source_views.py). The preview is a display convenience, with evidence type and timestamp role explicitly retained. It does not certify normalized acceptance or an evidence-quality grade.

MongoDB remains the agreed durable store. The existing evidence/dashboard ingestion path still has its own adapters and store. The expanded statewide source path has not been wired into a production normalization, quarantine, quality-assessment or persistent event pipeline. Process snapshots and local fallback JSON are temporary caches. Remote NOAA file references have rolling retention and need durable blob retention for long-term replay.

Future agents should preserve originals and independently handle validity, evidence quality, current freshness and downstream operational priority. Avoid a single confidence percentage. Deduplicate shared measurements across USGS, NWPS and LCRA before treating agreement as corroboration. A gage reading, rainfall estimate or forecast runoff value cannot establish inches of water on pavement.

## Credentials, setup and verification

- Configure `DRIVETEXAS_API_KEY` in the ignored root `.env`. The application loads environment settings on startup. No real key belongs in code, fixtures, request metadata, logs or this document.
- The configured key successfully accessed WZDx. The general `conditions.geojson` request returned HTTP 401. General flood-closure access remains pending. The construction endpoint has separate product coverage.
- Other connected sources above were accessed without credentials. TranStar access is pending. Website-backed internal endpoints may change without a published API guarantee.
- Backend setup uses Python 3.12 and `uv sync`. Rasterio is now required for GRIB2 decoding. Run `uv run uvicorn app.main:app --reload` from `backend/` with MongoDB available. Run `npm run dev` from `frontend/`.
- Start the local MongoDB replica set with `scripts/start-mongodb.ps1` on Windows. Real database tests use `MONGODB_TEST_URI` and isolated test databases.
- Latest completed verification passed 412 backend tests with MongoDB enabled, 81 frontend tests, the frontend production build and live desktop/mobile browser checks.

## Highest-value next work

1. Resolve TranStar access and DriveTexas general-conditions permissions.
2. Verify SARiver timestamp timezone and obtain dated Austin closure confirmations.
3. Obtain actual camera images with capture times and implement image freshness/offline handling.
4. Decode/georeference Harris inundation rasters before road intersections or depth interpretation.
5. Verify FLASH product horizon/version, station datums, missing-value vocabularies and revision identities.
6. Implement the separate normalization, quarantine, quality and MongoDB integration milestone, with accepted observation IDs supporting persistent event transitions.
