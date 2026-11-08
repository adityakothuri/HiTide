---
tags: [floodwatch, experiment, demo]
status: done
updated: 2026-11-07
---

# 2026-11-07 Demo run check (Phase 6)

**Goal:** confirm the scripted demo runs end to end on `main` after the frontend merge and the voice phase.

**Setup:** `PHOTON_MODE=mock SIM_PROFILE=demo uv run uvicorn app.main:app --port 8011`. A Python WS client connected, sent `POST /api/demo/start`, and recorded 110 s.

**Result:** pass. All 7 `demo.step` events fired in order and no waits timed out. Total about 61 s.

| Event | Count |
|---|---|
| drivers.update | 110 |
| drone.update | 65 |
| outreach | 17 (12 pre-trip texts including a teen's parent copy, 2 in-app TTS, 1 driver voice, family text + voice) |
| segments.update | 14 |
| reroute | 10 |
| counters | 8 |
| case.update | 6 (monitoring → calling → contacting_family → drone_en_route → handed_to_responders; the timeline records verified) |
| turn_around | 2 (demo-b at 18 s, background d-043 at 52 s) |

Final counters: warned 11, rerouted 2, stopped 1, people verified 1. Vision: water at windows, 1 on roof (0.74), boat required, night thermal flagged simulated.

**Notes**
- High-risk cases go `verified` → `handed_to_responders` in the same transition, so the frontend sees one `case.update`. Verified is visible in the timeline.
- The mock call gap is 12 s. A live `photon2` call takes 10-20 s to connect, so run once on real phones before stage.
- The frontend's `src/demo/recording.json` replay still has the old $15k-based counter values. The live WS is unaffected.

Related: [[Demo Script]] · [[00 Home]]
