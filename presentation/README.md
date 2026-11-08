# Presentation kit: everything in one place

Everything a presenter needs is in this folder. The files are **copies**: the originals stay where the app and docs use them, so you can rename, drag or delete anything here without breaking anything.

## Start here

| What | Where |
|---|---|
| **Slide deck: drone vision** (interactive, private link; ask Aditya to share it) | https://claude.ai/artifact/6DMkWUJnKCWvEien2aFEtu |
| **Test evidence page** (interactive, private link) | https://claude.ai/artifact/HAjyBQR6k1YhaLcL54Ps4w |
| Pitch outline: problem, solution, why us | [`../vault/Pitch.md`](../vault/Pitch.md) |
| Demo script: what happens on screen, step by step | [`../vault/Demo Script.md`](../vault/Demo%20Script.md) |
| Test numbers: tests by layer, 16 safety guarantees | [`../docs/TEST_EVIDENCE.md`](../docs/TEST_EVIDENCE.md) |
| Drone vision accuracy write-up | [`../vault/Experiments/2026-11-08 Drone vision accuracy.md`](../vault/Experiments/2026-11-08%20Drone%20vision%20accuracy.md) |
| Whole project in one doc (what's real, what's mocked) | [`../docs/STATE_OF_THE_UNION.md`](../docs/STATE_OF_THE_UNION.md) |
| How to run the app for a live demo | [`../README.md`](../README.md) (`./dev.sh`) |

## Folders

### `1-charts/`: slide-ready graphs

**`drone-vision/`**
| File | Shows |
|---|---|
| `01_depth_error_by_condition.png` | Water-depth error in inches across 19 conditions (GPS, compass, altitude, river slope and others). Typically 2–4 in. |
| `02_failure_modes.png` | Where the model breaks: steep banks, vegetation, turbid shallows |
| `03_glare_vs_puddle_tradeoff.png` | Filtering out glare also deletes real puddles. This is the known critical bug, and the fix is planned. |
| `04_consistency_score.png` | The physics check that separates real floodwater (≥0.97) from glare (0.00) |
| `05_range_too_wide.png` | The uncertainty ranges are about 2.4× too cautious (honest, but needs calibration) |
| `06_rise_detection.png` | Drones measure level well but rise rate poorly, so the rate comes from the gauges |
| `07_coarse_dem_depth_vs_absolute.png` | On a 10 m elevation map, depth stays accurate even when absolute elevation is off |
| `08_drone_corrects_gauge_model_illustration.png` | Concept: drone readings correct the gauge-driven flood model near critical points |
| `09_real_photo_person_on_car_alert.jpg` | Real photo: person on a car roof in water, which raises an alert |
| `10_kerrville_cp0014_depth_reading.jpg` | Simulated drone reading at Kerrville critical point CP-0014 |

**`test-evidence/`**
| File | Shows |
|---|---|
| `tests_by_layer.png` | 811 passing tests, grouped by system layer |
| `stress_recall.png` | Safety pipeline stress test: 2,000 users replayed through July 4, 2025 |
| `replay_levels.png` | Danger levels over the July 4, 2025 replay timeline |

### `2-app-screens/`: screenshots of the product

- **`ops-console/`**: the operator dashboard.
  - `after-1440-*`: the latest redesign. Covers the flood monitor (day and night), risk hover, inspections, driver cases, data sources and present mode.
  - `wx-console-*`: the July 4 weather replay at 02:00, 04:30 and 06:30, plus a gauge view.
  - `audit-1440-*`: the statewide Texas view, the exercise mode and present-mode stills at 5, 30 and 65 s.
- **`driver-web/`**: the driver journey in order.
  - `1-home` → `2-warning` / `2a-push` → `3-turn-around` → `3b-new-route` → `4-check-in` → `4a-incoming-call` → `4b-call-connected` → `5-help` → `6-claim` → `7-settings`.
- **`mobile-app/`**: the phone app.
  - `polish-*`: the final UI, in flow order 01–12.
  - `live-*`: the app running against the live backend: home, turn-around, check-in, support, offline.

### `3-design/`
- `hitide-logo.png`
- `mockups/`: phone driver flow, desktop inspections, desktop driver cases, iPad flood monitor and the two consumer flows

### `4-drone-vision-photos/`: what the drone "sees"
- `flood_0X_annotated.jpg`: real flood photos with the model's overlays (water mask, YOLO boxes, depth reading).
- `flood_01_thermal.jpg`: a **simulated** thermal view, not real infrared.
- `cp-0014_*.jpg`: snapshots from the Tello drone and the simulation at critical point CP-0014.
- Credit the authors when you show these. Licences (CC BY / public domain) are in `SOURCES.md`.

### `5-flood-videos/`: the model running on real Kerrville flood video
Open the MP4s directly; they play in QuickTime or any browser.

| File | Shows |
|---|---|
| `1_riverside_dr_car_flood.mp4` | July 4, 2025, Riverside Dr bridge. YOLO boxes on cars and people next to the flood, plus a water-height key. |
| `2_ingram_truck_submerged.mp4` | A truck submerged in Ingram. **This is from the July 16, 2026 flood, not July 4, 2025.** |
| `3_dietert_river_trail_model.mp4` | July 4, 2025, River Trail. The **model's own** water-height estimate: 1,611 ft, 85% chance within ±1 ft. |
| `*_poster2.jpg` | A still from each video, for slides |

How to read the water-height key:
- The big number is the water surface elevation in ft (NAVD88).
- **CI95** is the 95% range.
- **P(±1ft)** is the chance the true level is within 1 ft: green is good, yellow is OK, red is low.
- On clips 1 and 2 the number comes from the USGS gauge. On clip 3 it comes from our model, which reads the waterline in the image and checks it against 1 m lidar.

Say **"internal demo"** and keep the on-screen credit; we don't have rights to redistribute this footage. Full credits are in `SOURCES.md`.

## Wording to keep honest on stage
- The drone model is a **prototype**. It is tested on synthetic scenes plus real footage; it hasn't been flight-tested over a real flood yet.
- The thermal image is simulated, and the Ingram truck clip is from 2026.
