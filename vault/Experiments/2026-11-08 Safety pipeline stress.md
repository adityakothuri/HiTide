---
tags: [hitide, experiment, safety]
date: 2026-11-08
code: backend/scripts/stress_safety.py
data: data/experiments/safety_stress_*_2000.json, data/experiments/safety_load_*.json
---

# Safety pipeline stress: July 4, 2025 replay, 2,000 simulated users

**Setup.** `uv run python scripts/stress_safety.py --users 2000 --fault <f>`.
- The replay runs from 01:00 to 07:30 CDT with a 120 s loop step.
- The population mix is 615 users at a crossing (±30 m), 985 at home in populated areas, and 400 driving random routes at 13 m/s with a ping every step.
- Each user has a fixed reply persona: 60% answer SAFE, 10% ask for HELP, 30% never answer.
- The system only sees **belief**: gauges, NWS, radar, storm reports and simulated drones. It is scored against the replay's **truth** depths, which it never sees.

**Truth.**
- **Exposed:** at least 6 in of water within 150 m of the user at some point. 1,361 of the 2,000 users were exposed. The users are deliberately placed at the water, and this was the worst night on record.
- **False alarm:** rated DANGER or worse, but truth stayed under 3 in within 400 m all night.

## Results

| Scenario | DANGER recall before water | DANGER lead, median / p10 | WARNING recall | WARNING lead, median | False alarms (share of flagged) | Messages per user, median / p95 / max |
|---|---|---|---|---|---|---|
| Baseline | **82.6%** | **110 / 22 min** | **100%** | 210 min | 9.9% (163 / 1,650) | 6 / 11 / 17 |
| All USGS gauges dark from 04:00 | 79.5% | 117 / 22 min | 100% | 210 min | 10.2% | 6 / 10 / 16 |
| NWS alerts down (before fix) | 24.8% | 22 / 0 min | 56.1% | 115 min | 3.8% | 2 / 10 / 17 |
| NWS alerts down (after fix) | **58.3%** | 118 / 36 min | **98.5%** | 136 min | 9.3% | 3 / 9 / 16 |
| Every source marked stale | 82.6% | 110 / 22 min | 100% | 210 min | 9.9% | same as baseline |

- **Stale data:** every assessment is marked confidence `low`, and the levels are unchanged. Stale data is still the best evidence, and it is labelled honestly.
- **NWS fix:** with NWS down, the pipeline originally let 1,092 users fall to NONE, reading missing data as "all clear". The fix (`hazard._findings`): when `nws_alerts` is degraded, a rising gauge anywhere in the region or heavy rain stands in for a Flash Flood Warning. Unchecked crossings and rising creeks then still escalate.
- **Message volume:** before the reminder cap and per-user reply personas, the median was 13 messages per user with a max of 26 (first 250-user run). Now it is a median of 6 over 6.5 hours of the worst flood on record, counting the parent, family, all-clear and acknowledgement messages.

## Latency

These runs were measured with 3 to 5 simulations sharing the CPU, so solo numbers are lower.

| Measure | Result |
|---|---|
| Per-ping assessment | 0.6–1.1 ms median, 5 ms p99 (about 1,000 pings/s on one thread) |
| Full refresh, 2,000 users (400 driving) | 0.43 s median |
| Full refresh, 250 parked users | 11 ms (warm neighbourhood cache) |
| Full refresh, 5,000 users all moving | 2.6 s median |
| Full refresh, 20,000 users all moving | 11 s |

The live loop steps every 30 s, so 5,000 users fit easily. 20,000 all-moving users need vectorized assessment or sharding.

## What it means

- **Everyone exposed was warned first.** Every user who ended up near deep water got at least a WARNING first, with a median of 3.5 h warning. 83% got DANGER (a poll, then a call) a median of 1 h 50 min before the water arrived.
- **Most of the DANGER misses are drivers.** A driver's position changes each step, and the heading cone sees water only within 800 m.
- **Most false alarms are low-ground homes during the area-wide Emergency.** That is defensible: the NWS called it catastrophic.
- **Limits:**
  - Truth for ungauged creeks is modeled (donor gauges). See [[2026-11-08 July 2025 replay calibration]].
  - Replies are simulated.
  - Drones are simulated.

Code: [[Per-User Danger]].
