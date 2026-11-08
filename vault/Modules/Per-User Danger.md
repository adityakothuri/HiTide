---
tags: [floodwatch, module, safety]
status: done
updated: 2026-11-08
code: backend/safety/
---

# Per-User Danger

**Question it answers:** is *this* opted-in person in danger *where they are right now*, and who do we contact, how hard?

It stitches together three features that used to be separate:

- live Texas feeds ([[Live Observations]])
- driver profile risk ([[Risk Scoring]])
- outreach ([[Photon Outreach]])

It runs on the Hill Country loop in **replay** (July 4, 2025) and **live** (real feeds now).

## Pipeline

| Step | Module | What it does |
|---|---|---|
| Position | `motion.py` | Turns pings into parked, driving or stopped. Moves smaller than the GPS jitter floor (25 m, or the reported accuracy) are noise. Out-of-order and duplicate pings are ignored. |
| Hazard at that spot | `hazard.py`, `context.py` | Snaps the position to roads (25 m densified KD-tree). It then reads the loop's **belief**: depth on your road; roads and crossings within 400 m; NWS polygons (zone-only alerts apply only inside the region); gauge rising or category; NWPS forecast; MRMS rain; storm reports; and, while driving, water in the heading cone. **Unknown depth is `null`, never dry.** |
| Hazard level | `classify_hazard` | Thresholds are 3 / 6 in and *your vehicle's* stall depth. On high ground at rest, area-wide alerts soften to WATCH. Outside the region the level is capped at WARNING. A Flash Flood Emergency covering a whole zone is DANGER only on low ground (< 5 m above water). |
| Vulnerability | `vulnerability.py` | One model with weights summing to 1, each concept counted once. Night comes from the local clock. The vehicle factor comes from stall depth. Needs, a teen driver and hearing loss change the channel. |
| Danger | `danger.py` | Starts from the hazard level. Stopped in water is CRITICAL. High vulnerability or a teen driver raises the level one step. NONE stays NONE, and the level is never lowered. |
| Ladder | `policy.py` (pure) | WATCH: text. WARNING: text, or spoken while driving, plus a copy to a teen's parent. DANGER: poll, then a call, then family. CRITICAL: call and open a case, then family and responders. Timers shrink for vulnerable users. Cooldowns and a reminder cap limit repeats. SAFE mutes the level; HELP flags responders. The all-clear is held while help was requested, a case is open, or evidence is dark. |
| Glue | `monitor.py` | Runs after every loop step and every ping. Each user's actions are dispatched independently. It watches voice calls; an unanswered call goes to family. An epoch guard discards results from before a reset. |

API: `docs/api-contract.md` → "Per-user danger". Inbound SMS replies (English and Spanish) reach it through `outreach/inbound.py`.

## Decisions

- **Belief, not truth.** The pipeline only ever sees what the system could know: gauges, NWS, radar, reports and drones. The stress test scores it against replay truth that it never sees.
- **No fake "sent".** In live mode a non-allowlisted number logs `suppressed`. Real sends go to `DEMO_PHONE_*`, or to enrolled +E.164 users only when `OUTREACH_ALLOW_ENROLLED=1`. They go to the driver's own number only; an unverified contact is never sent to.
- **Privacy.** For enrolled (real) users, the API shows the first name only and a home rounded to about 1 km. The exact position is shown only at DANGER or above. Phones never appear in responses, events or logs. They live only in gitignored `data/user_registry.json`.
- **Family SAFE is a note.** It doesn't stop us checking on the driver.

## Later (stacked on top)

- Critical-point tracking and the custom drone vision model feed the same `SafetyContext`: drone snapshots already change point status, which this module reads.
- Persisting `ResponseState` across restarts. Positions persist today; ladders don't.

See [[2026-11-08 Safety pipeline stress]] for accuracy, spam and latency numbers.
