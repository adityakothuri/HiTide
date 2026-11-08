# Consumer app — white and royal blue

Revision of the initial phone mockup following the user's feedback. This direction applies to the consumer phone app; it does not establish a new monitoring-dashboard palette.

## Image boards

- `01-consumer-overview-routes-updates.png`: overview, route planning, updates.
- `02-consumer-safety-flow.png`: urgent turn-around alert, stationary check-in, support status.

Generated using the built-in Imagegen tool, with the user's supplied screenshot as a composition reference. The exact prompt for each board is saved alongside it.

## Direction

- Primary palette: white and royal blue (`#2448E8`); dark navy text, secondary slate, and pale blue supporting surfaces.
- Strong solid-blue headers, large quiet maps, anchored action panels, deliberate whitespace, and a coherent native phone hierarchy.
- The supplied reference informs composition. Its red identity, payment cards, financial charts, and text are excluded.
- No State Farm name, logo, brand colors, insurance policies, claims navigation, or insurer disclaimers in these concepts.
- Hazard accents are semantic exceptions: small amber warnings and emergency call affordances, not competing brand colors.
- General screens use Home / Trips / Updates / Profile navigation. Urgent and check-in states focus on the immediate task.
- Show current observation context and alternative routes without certifying a route as safe. The support status uses sample data and explicitly simulated workflow language.

## Review notes

These are raster UI concepts, not implemented app screens. Sample place geometry, timestamps and status content are illustrative. Build actual maps from repository data, establish one canonical vector mark, and verify screen sizes, accessibility, and API behavior during implementation.

The current app's separate evidence and driver-simulation paths remain relevant; see the parent README for repository findings and reference research.
