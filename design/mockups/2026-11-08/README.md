# HiTide image mockups

Generated November 8, 2026 with the built-in Imagegen tool. These are raster design concepts with illustrative data and geography, not implemented interfaces or validated live conditions. The user requested images first; application code has not been redesigned in this pass.

## Deliverables

1. `01-phone-driver-flow.png`: overview, pre-trip warning, voice-led turn-around alert, stationary safety check-in.
2. `02-desktop-inspections.png`: laptop/desktop evidence queue, local map, crossing inspector, source health.
3. `03-desktop-driver-cases.png`: laptop/desktop driver case queue, map, outreach history, simulated visual evidence.
4. `04-ipad-flood-monitor.png`: tablet-specific regional monitor, source filters, touch controls, selected county sheet.

The matching `.prompt.txt` files preserve the exact generation prompts. All four concepts use an independent HiTide identity with no State Farm name, logo, insurer navigation, or red brand treatment. Existing production source and historical documentation still contain the previous branding; removing it from the running app belongs to implementation after image review.

## Product understanding from the repository

The repository contains three related frontend experiences, backed by two distinct workflows:

- The statewide monitor (`frontend/src/evidence/TexasMonitor.tsx`) lives at `/` and `/texas`. It searches and filters source observations, time windows, and geographic evidence. It preserves unavailable/partial sources and distinguishes source context from current observations.
- The local evidence workspace (`frontend/src/evidence/Operations.tsx`) currently owns `/console`. It shows road access, evidence freshness and conflicts, neighborhood connectivity, prioritized inspection tasks, community reports, and inspection assignment/completion.
- The driver app (`frontend/src/driver/DriverApp.tsx`) lives at `/driver`. A pure screen derivation in `frontend/src/state/driverFlow.ts` moves among calm, warning, turn-around, check-in, help, and resolution states. Settings include consent and emergency contacts. Existing insurer-oriented claims/home navigation should be reconsidered for the independent identity.
- The legacy driver operations console (`frontend/src/console/Console.tsx`) supports cases, outreach, map layers, drone state and visual evidence. It is embedded in `/present`; the current `/console` route returns the newer evidence workspace before the legacy route switch. A future independent Driver cases navigation destination requires explicit routing work.
- The gallery and presenter views support demonstration and shared state. They are not separate end-user products.

The frontend is React 19, TypeScript and Vite. MapLibre uses CARTO/OSM basemaps and cached local geometry as fallback. Shared primitives and design tokens already exist, alongside separate evidence and driver styling.

The FastAPI backend has two parallel data paths:

1. Legacy simulation: cached Kerrville road graph/elevation, simulated flooding and driver movement, risk-ranked outreach, staged warning/reroute/escalation, Photon messaging and ElevenLabs voice adapters, simulated drone dispatch, and sample vision results. The driver UI consumes a WebSocket provider or recorded mock provider through a reducer/store.
2. Evidence workflow: source adapters normalize observations; MongoDB is the default persistent store, with explicit SQLite as an alternative. Road assessments retain access status, actual observation time, freshness and disagreement separately. Directed community connectivity identifies consequential uncertain crossings. Tasks move through queued, assigned, completed/inconclusive; operator findings become observations and recalculate road/queue state. The operations UI polls `/api/evidence/state` and posts report/task mutations.

The two paths are not currently one integrated operational system. The mockups present them as separate operator workspaces, not as proof of a shared live backend.

## Research and design rationale

Primary visual/product references reviewed:

- [Apple Maps](https://www.apple.com/maps/) and [Apple's iPhone Maps guide](https://support.apple.com/guide/iphone/get-started-with-maps-iph6ef6ef377/ios): geographic context, a clear route action, native phone hierarchy. Adopt map-plus-action composition and readable navigation; keep hazard interpretation explicit.
- [Linear features](https://linear.app/features) and [Linear concepts](https://linear.app/docs/conceptual-model): compact navigation, coherent selected rows, queue/detail hierarchy. Adopt disciplined density and progressive detail rather than oversized KPI cards.
- [Samsara telematics](https://www.samsara.com/products/telematics) and [its fleet dashboard example](https://www.samsara.com/ca/customers/ghilotti-bros-inc): map-centered operations with a linked asset list. Adopt queue/map coordination while preserving HiTide's evidence and inspection semantics.

These are reference patterns, not copied screens or endorsements. The proposed visual choices are design judgments based on the workflows above.

## Proposed shared visual language

- Retain the existing descriptive name HiTide; a small blue wave is an exploratory mark, not a finalized logo.
- White and cool gray surfaces, slate text, restrained cobalt actions. Amber means caution/uncertainty; red is reserved for closures or urgent situations.
- Precise sans-serif typography, thin rules, modest corners, consistent line icons. Use shape, icon and text as well as color for conditions.
- Desktop: stable navigation plus queue/map/inspector. Larger screens gain map space, not giant cards. At narrower laptop widths, switch between queue and details instead of compressing all panes.
- Tablet: compact icon rail and one docked sheet; maps retain useful area; controls target at least 44px touch areas. Portrait should use a bottom sheet rather than three columns.
- Phone: short sentences, one next action, clear emergency responses, native navigation in ordinary states. Urgent driving mode removes tabs and text entry and foregrounds voice guidance.

## Truth and implementation constraints

- Unknown access is not open. NWS warnings and gauge readings are context, not automatic road closures or road-depth measurements.
- Surface observed time, source category, stale/missing evidence, conflicts and unavailable feeds. Do not replace observation timestamps with fetch time.
- Do not imply that an alternate route is guaranteed safe, or show a numerical confidence the backend does not calculate.
- Physical drone control, live camera streaming and validated flood forecasting are not established by this repository. Keep sample imagery, simulated flights and outreach visibly labeled.
- Counts, times, locations and case states in these images are illustrative. Raster map geometry must be replaced by real map data in implementation. The inspection board's header count is illustrative and should be reconciled with actual rows/filters when built.
- Generated boards may vary slightly in mark shape and small spacing. Implementation should use one canonical vector mark and shared tokens rather than reproduce those inconsistencies.
- Image review does not substitute for responsive, keyboard, contrast, screen-reader, source-state or live API testing. No application tests were run for this image-only deliverable.

## Suggested implementation sequence after image review

1. Establish independent brand tokens/mark and replace visible insurer copy, metadata, notification/call identities and message templates; preserve historical records as appropriate.
2. Build the shared operator shell and real route ownership for Flood monitor, Inspections and Driver cases.
3. Adapt the existing evidence workflow to the desktop/tablet composition without merging it implicitly with the simulation store.
4. Restyle driver screens and remove insurer-specific navigation/content, preserving screen precedence and driving interaction rules.
5. Verify actual desktop/laptop/tablet/phone layouts and all live, cached, stale, partial, disconnected and simulated states.
