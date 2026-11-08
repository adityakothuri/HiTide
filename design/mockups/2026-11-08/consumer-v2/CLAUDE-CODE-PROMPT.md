# Build the Flood Watch consumer app with React Native + Expo

You are implementing the actual mobile app in this repository. Act as a senior React Native engineer with excellent native product design judgment. Build and run a polished, functional Expo consumer app that closely matches the supplied mockups. Do the work, inspect the result, and fix material issues; do not stop at a plan, scaffold, or static screen.

## Workspace and visual references

Repository root:

`/Users/sidharthkumar/Documents/GitHub/hackUTD`

Open and visually inspect these two local images with your image-reading tool before implementing. The paths are provided so the user does not need to upload them again:

1. Everyday experience — overview, route planning, updates:
   `/Users/sidharthkumar/Documents/GitHub/hackUTD/design/mockups/2026-11-08/consumer-v2/01-consumer-overview-routes-updates.png`
2. Safety experience — turn-around alert, check-in, support status:
   `/Users/sidharthkumar/Documents/GitHub/hackUTD/design/mockups/2026-11-08/consumer-v2/02-consumer-safety-flow.png`

These two boards are the visual authority for the consumer app. The original inspiration screenshot is secondary and optional:

`/Users/sidharthkumar/Downloads/Screenshot 2026-11-08 at 1.38.39 AM.png`

If the optional screenshot is unavailable, proceed using the two committed boards. Do not use the older mockups in the parent directory as the design target. Read the adjacent `README.md` and the parent `README.md` for design intent and repository analysis. Inspect the source when older documentation disagrees with it.

Important: each board contains three different app screens in presentation phone frames. Implement the actual screens, not the board, phone bezels, board captions, studio background, or a giant image of the mockup. The app itself must be native, interactive React Native UI.

## Scope and stack

- Build only the consumer mobile app in this task, for iOS and Android, with React Native, Expo, and TypeScript.
- White and royal blue is the consumer app palette. Do not redesign the monitoring website or change its palette in this task.
- SpaceTimeDB is the intended future backend. Do NOT install, configure, deploy, connect, or implement SpaceTimeDB now. Do NOT write database schemas, server reducers, generated bindings, authentication servers, or cloud infrastructure. Create a small typed data-access boundary and a working local mock implementation so a future SpaceTimeDB adapter can replace it without rewriting screens.
- First inspect the repository for an existing Expo/mobile app. Extend it if present; otherwise create a focused `mobile/` app at the repository root. Preserve the existing `frontend/`, backend, and sidecar applications. Do not convert the Vite website in place.
- Use a currently supported stable Expo SDK and SDK-compatible packages. Check official Expo/library documentation for compatibility before choosing native dependencies; use the Expo package installer where appropriate. Respect the repository's package-manager conventions.
- Prefer Expo Router unless the existing native app already has a suitable navigation system. Use ordinary native components and a shared design-token layer. Do not build a WebView wrapper or import browser-only UI packages.
- Keep the architecture small and comprehensible. One mock repository, shared domain types, a focused state reducer/store, reusable primitives, and screen components are enough. Avoid speculative infrastructure and unnecessary dependencies.

## Product truth to preserve

Flood Watch is an independent flood safety app for people traveling through flood-prone areas. It helps users review relevant flood information, reconsider affected trips, hear turn-around alerts, respond to safety check-ins, and see the status of a help request.

Inspect these existing files for domain behavior, not for visual styling:

- `frontend/src/state/driverFlow.ts`
- `frontend/src/state/cases.ts`
- `frontend/src/data/types.ts`
- `frontend/src/data/provider.ts`
- `frontend/src/driver/DriverApp.tsx`
- `frontend/src/driver/screens/Warning.tsx`
- `frontend/src/driver/screens/TurnAround.tsx`
- `frontend/src/driver/screens/CheckIn.tsx`
- `frontend/src/driver/screens/Help.tsx`
- `frontend/src/driver/screens/Settings.tsx`
- `docs/api-contract.md`

Do not blindly carry over legacy insurer content, profile fields, or claims flow. The existing evidence/inspection workflow and driver simulation have separate data paths; this task does not integrate them or migrate the backend.

## Non-negotiable visual requirements

- Remove ALL State Farm branding from the new mobile app: names, logos, red brand styling, insurer disclaimers, insurance products, policies, claims, and insurer-specific navigation. Check visible text, accessibility labels, app metadata, splash screen, icons, sample notifications, and fixtures. Do not merely replace the logo while retaining the old insurer app structure.
- Do not globally rewrite historical documentation or mutate existing backend message templates as a side effect. The new app must have no insurer branding in its own assets, metadata, fixtures, or rendered content.
- App name: **Flood Watch**. Use one consistent, simple wave mark derived from the boards. Make it a lightweight vector asset or component, not a cropped bitmap.
- Primary royal blue: `#2448E8`. White: `#FFFFFF`. Main ink: `#13203B`. Secondary text: `#6D7890`. Supporting pale blue: `#EEF3FF`. Use semantic tokens; tune a secondary color if required for readable contrast.
- Royal blue and white should dominate. Amber is a small hazard accent; dark red is reserved for emergency-call affordances. No purple, turquoise, red brand header, ornamental gradients, glass effects, or dark dashboard styling.
- Match the boards' composition: confident blue headers, large calm maps, strong type hierarchy, generous whitespace, precise iconography, and anchored route/action panels. Avoid filling every gap with another card or badge.
- Use native platform typography, consistent weights, approximately 24px horizontal content margins, a disciplined spacing scale, roughly 18px major-panel corners and 12px control corners. Treat these as starting tokens; match the reference proportions on a real device.
- Use safe areas correctly: blue extends behind the status bar where shown; white content and controls avoid the home indicator. No duplicate status bars or artificial notch inside the app.
- General navigation: **Home / Trips / Updates / Profile**. All four tabs must work. Urgent and check-in flows hide ordinary tabs and focus on the immediate task.
- Adapt naturally to narrow phones and Android font metrics. Do not hard-code a screenshot-height canvas or crop content to mimic one iPhone. Respect font scaling, accessible contrast, and touch targets of at least 44pt on iOS / 48dp on Android.

## Build these screens and interactions

### 1. Home / overview

Follow the first phone on board 1: blue header, Flood Watch mark, greeting for Dana, initials avatar, location, overlapping white warning strip, large muted map, and a restrained “Before you go” list.

- Warning strip opens warning details, including source and issued time.
- The work-trip row opens route planning.
- Emergency-contact row opens contact details/editing.
- Avatar opens Profile.
- Show real screen-specific content; do not turn every tap into an alert saying “coming soon.”

### 2. Trips / route planning

Follow the second phone on board 1: compact blue header, a large map, blue alternate route, gray dashed original route, a closure marker, and an anchored white route sheet.

- Display Home → Work, illustrative distance, affected road, and source context.
- “Review alternate route” opens useful route details. Allow the user to select the alternate route and reflect that choice in Trips and Updates.
- Keep map controls, route details, and lower actions usable with safe-area insets.
- Call the route an alternate route, not a guaranteed safe route.

### 3. Updates

Follow the third phone on board 1: blue header, light content surface, filter tabs, and well-spaced timestamped rows with thin dividers.

- Filters All / Trips / Check-ins actually filter the local data.
- Warning and route entries open the relevant detail.
- Read/unread state updates after viewing an item.
- The privacy/settings helper opens the relevant Profile section.
- Use a coherent fictional persona and emergency contact across all screens. For this demo, use Dana Whitfield and Maria Whitfield consistently rather than mixing the old repository personas.

### 4. Urgent turn-around alert

Follow the first phone on board 2: confident royal-blue instruction area, a large white turn-around arrow, clear instruction, muted map below, and one primary route action. Hide the normal tab bar.

- Make this state reachable through the local scenario controls.
- Use a compatible native speech capability for the spoken alert; respect the user's voice setting and avoid repeated speech on ordinary rerenders.
- “Show alternate route” acknowledges the alert and opens the appropriate route state.
- No typing or dense interaction while driving. A muted or unavailable speech capability must not block the visible alert.

### 5. Safety check-in

Follow the second phone on board 2: “Are you safe?”, brief explanation, current-location map, location row, and two large separate actions: “I'm safe” / “I need help.”

- “I'm safe” updates the local case, shows a clear confirmation, and returns to a sensible resolved state.
- “I need help” enters support status and records the action once; prevent duplicate submits.
- Reserve this interaction for a simulated stopped state.
- “Call 911” must not silently place a call. For the demo, show a clear confirmation sheet identifying this as a prototype; do not contact emergency services during development or testing.

### 6. Support status

Follow the third phone on board 2: acknowledgement, location map, and an orderly progress timeline with actual local event timestamps.

- Include help-request receipt, simulated emergency-contact notification, and awaiting-operator state.
- Show a demo/sample-data indicator. Do not claim a real call, text, responder dispatch, live drone, or guaranteed response time.
- Contact-details action works; exit/back behavior preserves the active case correctly.

### 7. Profile and preferences

Extend the established visual system for the screen not explicitly pictured: identity, editable emergency contact, location-sharing preference, spoken-alert toggle, and a test-voice action.

- Persist appropriate local preferences, contact edits, read state, and selected trip.
- Do not persist a one-time urgent overlay in a way that traps the app after restart.
- Permission denial must have a clear fallback. Do not request background location or push-notification infrastructure for this mock-backed milestone.

## Maps, local data, and future backend boundary

- Use a real Expo-compatible native map implementation where supported, with a calm light style, useful markers, and route polylines. Check Expo Go versus development-build requirements and document them accurately.
- Prefer an implementation that does not need new paid credentials just to review the iOS demo. If a platform needs a map key, document the setup and provide a deliberate, well-rendered local vector fallback. Never leave a blank map, endlessly spinning loader, broken tiles, or a static crop of a mockup.
- Repository geography in `data/town/` and `frontend/public/town/` may inform Kerrville fixtures. Do not import the entire road graph into every screen. Use a small, checked local fixture and geographic coordinates appropriate to the illustrated route.
- Routes, flood conditions, timestamps, and case events are demo data. Map tiles can be real while the scenario remains explicitly simulated.
- Define only the domain types needed now: user/preferences, contact, trip/route, warning/update, and safety case/events. Provide typed methods to read/subscribe to current state and perform the actions above. Keep all screen data access behind this boundary.
- Implement the mock adapter with deterministic fixtures, reactive updates, clean subscription teardown, realistic async states, and errors that can be exercised. Do not sprinkle independent hard-coded data arrays inside screens or invent a SpaceTimeDB API.
- Provide unobtrusive development-only scenario controls for Normal, Flood warning, Alternate route, Turn-around, Check-in, Help requested, Resolved, and Reset. Every major reference state should be reviewable immediately without waiting through a long scripted timeline. Keep these controls outside the ordinary consumer navigation.

## Execution and validation

1. Inspect the repository, applicable instructions, both visual boards, and relevant state logic. Briefly state the implementation location and plan, then proceed without waiting for approval on routine reversible choices.
2. Build the native shell, visual tokens, data boundary, and all screen states. Implement real navigation and local interactions, not disconnected mock screens.
3. Run the appropriate TypeScript, lint, and Expo configuration checks. Add focused tests for meaningful state transitions: safe/help actions, urgent-alert precedence, route acceptance, and preferences. Do not create snapshot tests that simply repeat the markup.
4. Run the app in an available simulator/emulator. If one is unavailable, use the strongest available execution check and clearly report the limit. Do not claim native verification based only on a web preview.
5. Capture and inspect screenshots of all six reference states. Compare them directly with the image boards for header proportions, map area, alignment, type hierarchy, spacing, buttons, and bottom insets. Check at least one smaller phone viewport and Android layout if available. Fix the material issues found in a bounded visual pass.
6. Exercise the full flow: Home → route review → alternate selection → Updates → urgent alert → route acknowledgement → check-in → help status; separately verify the safe response, settings, contact edits, restart behavior, and reset.
7. Search the new mobile app for residual State Farm/insurance/claims branding. Keep legitimate emergency red distinct from banned red brand styling.
8. Save concise setup/run instructions in the mobile app README, including the exact working launch commands, scenario-control entry point, any map setup, mock-data limitations, and where the future SpaceTimeDB adapter belongs.

Preserve unrelated work and existing apps. Do not delete/reset the repository, commit or push changes, deploy services, or send real messages. If a nonessential external integration is unavailable, keep the mock-backed app functional and document the limitation. Ask a question only for a genuine blocker that cannot be resolved from the repository and this brief.

## Definition of done

A runnable React Native + Expo consumer app with a cohesive white/royal-blue identity; the six pictured screens plus working Profile/settings; real navigation and local state transitions; reliable map presentation or an intentional fallback; no State Farm branding in the new app; no backend/SpaceTimeDB implementation; and verified visual and functional behavior to the extent the environment supports.

In your final handoff, report what you built, the app directory, exact run command, screenshot locations, checks actually run, material limitations, and the single data boundary to replace when SpaceTimeDB is implemented. Keep it concrete.
