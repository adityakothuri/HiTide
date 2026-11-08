---
tags: [floodwatch, demo]
status: todo
updated: 2026-11-07
---

# Demo Script (90 seconds)

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

## Talk track

> [!todo] Write the narration once the demo is running end to end.

## Backup

> [!todo] Record a full backup video of a run (ECC `ui-demo` skill).
