---
tags: [hitide, module, frontend]
status: built
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

## Built (2026-11-07)

- Shell: app bar (wordmark, settings gear), bottom tabs Home / Trips / Claims / Profile (all work; Profile is HiTide settings). Phone frame with a status bar when shown on desktop or in `/present`.
- 5.2 route card is a small SVG map (`RouteMap.tsx`): nearby roads, flooded roads on the water scale, the blocked segment and a critical pin, the safer route in green. The primary action is sticky above the tab bar.
- 5.3 takeover: `role="alertdialog"`, the rest of the app is `inert`, focus goes to "Show new route" and returns to the new heading after. Speaks the backend message via `speechSynthesis`; the button only says "Speaking" once audio actually starts (browsers block speech before a user gesture, so press "Test spoken alert" in Settings once before presenting).
- 5.4 replies go to `POST /api/cases/{id}/reply` in live mode (verified against the backend: "I need help" moves the case to "Driver needs help" then "Handed to responders").
- Call 911 never dials in the prototype; it shows a toast.
- Screenshots: `vault/Experiments/screenshots/cp3-driver-*.png` (`npx playwright test e2e/driver.spec.ts`).

## Code

- `frontend/src/driver/`: `DriverApp.tsx`, `useDriverView.ts`, `RouteMap.tsx`, `speech.ts`, `screens/`
- `frontend/src/state/driverFlow.ts`: screen derivation + help timeline steps
- `frontend/src/data/personas.ts`: persona overlay

## Related

- [[Stage 1 Pre-trip]], [[Stage 2 En route]], [[Stage 3 Stopped in water]], [[Dashboard]]
