---
tags: [floodwatch, module, frontend]
status: in-progress
updated: 2026-11-07
---

# Driver App

The phone view a State Farm customer sees, at 390×844. It's meant to feel like a screen inside an insurer's existing app. Design: [[Design System]].

## Screens and when they show

`deriveDriverScreen()` in `frontend/src/state/driverFlow.ts` (tested) picks the screen:

| Screen | Shows when |
|---|---|
| 5.1 Home, calm | Nothing affects this driver |
| 5.2 Warning | The driver got a pre-trip text while a warning is active, **or** dismissed a turn-around (then it shows the new route) |
| 5.3 En route takeover | A `turn_around` event arrived for this driver |
| 5.4 Check-in | A case exists in `monitoring`, `calling` or `contacting_family` |
| 5.5 Help on the way | The driver tapped "I need help", or the case reached `drone_en_route` or later |
| 5.6 Claim started | The driver tapped "I'm safe", or the case is `resolved` |
| 5.7 Settings | Gear icon on Home |

Precedence: case, then turn-around, then pre-trip warning, then calm.

## Which driver

`/driver?driver=demo-d` pins one driver. Without `driver`, the phone follows `focusDriverId`, which the reducer sets on the latest pre-trip, turn-around or case event for a **demo** driver. Demo drivers get realistic persona names from `frontend/src/data/personas.ts`: Dana Whitfield (pre-trip), Luis Ortega (en route), Margaret Hale (stalled, daughter Maria).

## Code

- `frontend/src/driver/` (Phase 3)
- `frontend/src/state/driverFlow.ts`: screen derivation + help timeline steps
- `frontend/src/data/personas.ts`: persona overlay

## Related

- [[Stage 1 Pre-trip]], [[Stage 2 En route]], [[Stage 3 Stopped in water]], [[Dashboard]]
