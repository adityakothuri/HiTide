---
tags: [hitide, demo]
status: in-progress
updated: 2026-11-07
---

# Demo Script (about 60 seconds of run, 90 seconds of talk)

Triggered by the **Demo** control (`POST /api/demo/start`). Timers are compressed and the seeds are fixed, so every run plays out the same way. See [[Stage 1 Pre-trip]], [[Stage 2 En route]], [[Stage 3 Stopped in water]].

| # | What happens | Who / what the audience sees | Backend events |
|---|---|---|---|
| 1 | A flash flood warning hits Kerrville. Roads near the Guadalupe turn red. | Ops map + alert banner | `alert`, `segments.update` |
| 2 | Teammate A gets a pre-trip text with a safer route. | Teammate A's real phone + driver view card | `outreach` (text), `reroute` |
| 3 | Teammate B is driving toward a flooded crossing. The driver view shows "Turn around" and the map reroutes. | Driver view (spoken alert) + ops map | `turn_around`, `reroute` |
| 4 | A simulated older driver (Margaret Hale, 78) stops in a flooded low spot at night. Photon calls her; no answer. | Case card opens in the ops queue | `case.update` (calling), `outreach` (voice) |
| 5 | Teammate C (her daughter) gets a text and a call. The case is flagged to responders. | Teammate C's real phone + case timeline | `outreach`, `case.update` (contacting_family, responder_flag) |
| 6 | A drone flies there. Vision shows water at the windows and one person on the roof. Recommendation: boat required. | Drone animates on the map; the case card shows the image and boxes | `drone.update`, `case.update` (verified, vision) |
| 7 | Counters update. | Ops header | `counters` |

## Measured timing (mock mode, 2026-11-07)

Measured from `POST /api/demo/start` over the WS. Every step fired and nothing timed out. See [[2026-11-07 Demo run check]].

| Step | t (s) | Case state |
|---|---|---|
| 1 Warning | 0 | |
| 2 Pre-trip text | 6 | 11 drivers warned, plus a teen's parent copy |
| 3 Turn around | 9 (alert at 18) | |
| 4 Stopped, calling | 22 (case at 27) | `calling`, responders flagged at once (high risk) |
| 5 Family | 40 | `contacting_family` (+12 s) |
| 6 Drone | 46 | `drone_en_route` (+18 s) |
| 7 Verified | 61 | `verified` -> `handed_to_responders` (+33 s); vision: water at windows, 1 on roof, boat required |

Final counters: 11 warned, 2 rerouted, 1 stopped, 1 person verified, about $22k est. claims avoided ([[Pitch]] has the source and the assumption).

## Talk track

Pace about one line per step. Speak over the run. Don't wait for it.

1. **(Warning)** "It's night in Kerrville, Texas. The Guadalupe is rising. In July 2025 this river killed more than a hundred people, and most flood deaths happen in cars. A flash flood warning just hit, and HiTide turns the low roads red from real elevation data."
2. **(Pre-trip)** "Eleven opted-in State Farm drivers have a usual route that crosses one of those roads. They get a text *before* they leave, with a dry route. [Teammate A holds up their phone.] Teen drivers' parents get a copy."
3. **(Turn around)** "Teammate B is already driving. We never text a moving driver. Instead the app speaks: *Flooded road ahead. Turn around.* And it reroutes on dry roads before the water."
4. **(Stopped)** "Margaret is 78. She's stopped in rising water at night in a low-clearance car. Each of those raises her urgency, and none of them ever touches pricing. HiTide calls her right away and flags responders in parallel. [B's phone rings as Margaret.]"
5. **(Family)** "No answer. Twelve seconds later her daughter gets a text and a call. [Teammate C's phone.]"
6. **(Drone)** "A drone launches from the fire station. Vision runs on a real flood photo: water at the windows, one person on the roof."
7. **(Handoff)** "So the recommendation is a boat, not a truck. Responders get only what they need: location, people count, depth. The counters show the night: drivers warned, rerouted, one person verified, and the claims avoided."

Close: "Pre-trip, en route, stopped. Three chances to keep someone out of the water."

> [!warning] Check before stage
> Step 1's July 2025 fact: confirm the number before saying it, or drop the clause. Run the demo in `photon2` mode once on the real phones, because the live call at step 4 takes longer than the 12 s mock gap.

## Backup

> [!todo] Record a full backup video of a run (ECC `ui-demo` skill).

## Demo B: Hill Country critical points (replay of July 4, 2025)

`curl -X POST 'localhost:8000/api/demo/start?scenario=hill_country&speed=150'` replays 01:00 → 07:30 CDT in about 2.5 min. Beats are detected from the data, not hard-coded. Times below are from the 2026-11-08 run. See [[Critical Point Drones]].

| # | Sim time (CDT) | Beat | What the audience sees |
|---|---|---|---|
| 1 | 01:14 | Real Flash Flood Warning | `region.alert`. Crossings near the forks turn unknown. There's no gauge on the South Fork |
| 2 | 01:14 | Critical point #1 with its score breakdown, plus the top single-exit chokepoint (SH 39 over Cypress Creek: 138 households, 2 camps) | `critical_points.ranked` "why" panel |
| 3 | ~02:17–02:36 | Drone confirms water on a South Fork camp road | `snapshot.created`, a drone path on the map |
| 4 | ~02:17–02:50 | A riverside camp area is cut off: shelter in place, responders flagged, truck route or boat required | `node.updated`, area risk goes **severe** |
| 5 | ~03:00–04:30 | Instructions: Kerrville area gets a route out to high ground (text + poll, Teammate A); cut-off older resident gets a shelter call (Teammate B, "Ruth"); 15 s later her daughter gets a text + call (Teammate C) | Phones; `outreach` |
| 6 | 05:41 | The Hunt gauge goes dark (real: last reading a record 37.52 ft at 05:10) | `gauge.status` offline; drones re-plan |
| 7 | 07:30 | Counters, including households by risk band | `region.counters` |

**Line to land:** "In this replay the system cut off its first camp area and told it to shelter about 107 minutes before the real Flash Flood Emergency for Hunt went out."

**Say also:** this is a replay on real terrain, real gauges and real warning times. People, flights and snapshots are simulated, and the snapshots are generated from the flood model.
