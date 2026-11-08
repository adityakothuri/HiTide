---
tags: [floodwatch, pitch]
status: todo
updated: 2026-11-07
---

# Pitch

## Problem

Flash floods kill people in cars, and most drivers never see a warning tied to their own route. See [[Problem]].

## Solution

State Farm Flood Watch protects opted-in drivers in three stages:

1. **Before the trip:** a text that warns about closed or at-risk water on the driver's usual route, with an alternate route.
2. **On the road:** a "turn around" alert and reroute before the driver reaches the water.
3. **Stopped in water:** calls and texts to the driver, then family, drone verification, and a handoff to responders with location, people count, and depth. See [[Stage 3 Stopped in water]].

Everything runs offline from cache in the demo. Outreach runs in mock mode until Photon creds arrive.

## Why State Farm

> [!warning] To confirm with the team
> The plan says this is the State Farm track and the drivers are opted-in State Farm customers. The "why State Farm" argument was not in the plan file. Write it from the brief before the pitch.

## Proof from the demo

Counters from the 7-step run: warned, rerouted, stopped, people verified, and claims avoided. See [[Demo Script]].

> [!info] Claims figure (sourced)
> "Est. claims avoided" = unique drivers kept off a closed road (pre-trip warned on a blocking route, or rerouted en route) × **$19,943** average paid auto loss (Texas Dept. of Insurance, Hurricane Harvey data call, see [[Data Sources]]) × an **assumed 10%** who would otherwise have driven into the water. The 10% is our assumption. Say so on stage. The scripted demo shows about 11 drivers protected, which is about $22k.

## Next steps (out of scope for this weekend)

Based on the plan's deferred items. Confirm against the brief's out-of-scope list.

- Live Photon send and poll with real drivers (waiting on creds)
- Real-time feeds beyond the cached demo town
- Real drone footage and real thermal (night mode is simulated today)
- Towns beyond Kerrville
- Driver authentication and a production opt-in flow
- Integration with State Farm claims systems

## Related

- [[Architecture]]
- [[Privacy and Consent]]
