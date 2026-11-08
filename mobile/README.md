# Flood Watch — consumer app (Expo)

React Native + Expo (SDK 58) + TypeScript app for people traveling through flood-prone areas. It covers the overview, route planning, updates, the turn-around voice alert, the safety check-in, support status, and profile/preferences. All data is **local demo data**. There is no backend in this milestone.

Design reference: `design/mockups/2026-11-08/consumer-v2/` (two image boards). Screenshots of the running app are in `docs/screenshots/`.

## Run

Requires Node 22+ and Xcode with an iOS simulator (or a phone with Expo Go).

```bash
cd mobile
npm install
npx expo start          # then press i (iOS simulator) or scan the QR code with Expo Go
```

**Fast browser preview (no simulator):** with `npx expo start` running, open http://localhost:8081 (or press `w`). It renders the same screens with react-native-web at phone width, using the offline vector map instead of Apple/Google Maps. Use it for quick UI iteration; verify native behavior (maps, speech, safe areas) on a simulator or device. Scenario deep links work there too, e.g. http://localhost:8081/dev-action?do=check_in.

`npm run ios` / `npm run android` also work. On this machine, `expo start --ios` installed Expo Go but then failed on a macOS automation (osascript) permission. If that happens, open the app manually:

```bash
npx expo start
xcrun simctl openurl booted "exp://127.0.0.1:8081"
```

Checks:

```bash
npm run typecheck       # tsc --noEmit
npm run lint            # expo lint
npm test                # jest (reducer, mock repository, screen interactions)
npx expo-doctor
```

## Scenario controls (development only)

Every reference state can be reached immediately:

- **Long-press the Flood Watch mark** in any header, or use **Profile → Developer: scenario controls**. Choose Normal, Flood warning, Alternate route, Turn-around, Check-in, Help requested, Resolved, or Reset. A toggle simulates network write failures.
- **Deep link** (scripted review): `exp://127.0.0.1:8081/--/dev-action?do=<scenario|action>&to=<screen>`
  - `do`: any scenario above (`normal`, `flood_warning`, `alternate_route`, `turn_around`, `check_in`, `help_requested`, `resolved`) or an action: `safe`, `help`, `ack`, `select-alt`, `minimize`, `restore`, `dismiss`, `reset`
  - `to`: `home`, `trips`, `updates`, `profile`, `warning`, `route`, `contact`, `call`
  - Both parameters are checked against fixed allowlists. These controls do nothing in production builds (`__DEV__` only).

Add `?__expo_disable_fab=1` to the Expo Go URL to hide Expo Go's floating dev button for clean screenshots.

## Maps

- **iOS:** `react-native-maps` with Apple Maps (`mutedStandard`). Works in Expo Go and dev builds with no API key.
- **Android:** Works in Expo Go, which ships its own Google Maps key. A standalone/dev build needs your own key (`android.config.googleMaps.apiKey` in `app.json`, see the Expo `react-native-maps` docs). Without a key, set `EXPO_PUBLIC_MAP_MODE=vector`.
- **Offline vector fallback:** `src/map/VectorMap.tsx` draws the river, roads, routes and markers from a small checked fixture (`src/data/geo/kerrville.json`, ~87 KB). The fixture is derived from the repo's cached Kerrville road graph (`data/town/`). It is used on web and whenever `EXPO_PUBLIC_MAP_MODE=vector`.
- Route geometry is real (shortest paths on the cached OSM graph: the usual route via Riverside Drive, and an alternate that avoids low roads near the river). The closure, warning, times and case events are **simulated**.

## Architecture

```
src/
  app/            Expo Router routes (thin; re-export screens)
    (tabs)/       Home / Trips / Updates / Profile
    turn-around, check-in, support, resolved   focused flows (no tabs)
    warning, route-details, contact, call-911, dev   sheets
  screens/        screen components
  components/     primitives (Button, BlueHeader, Rows, Icon, WaveMark, SheetScreen)
  map/            FloodMap, native canvas, vector fallback, pure scene builder
  domain/types.ts the only shapes screens use
  state/          pure reducer (+ flow precedence), selectors, FlowGate navigation
  data/           repository interface, mock implementation, fixtures, React provider
  services/       speech (expo-speech, speaks each alert once)
  theme/tokens.ts colors, spacing, radii, type
```

- **Flow precedence:** safety case > turn-around alert > normal tabs (`deriveFlowMode`). `FlowGate` is the only code that moves the app into or out of focused flows. Before switching, it closes any open sheets.
- **Persistence (AsyncStorage):** contact, preferences, selected route, read state. Urgent overlays and safety cases are never persisted, so a restart always opens on the ordinary tabs.
- **Safety:** "Call 911" opens a prototype confirmation sheet and never dials. Contact notification, operator updates and any outreach are simulated and labeled as such. No messages are sent.
- **Permissions:** Location is requested (foreground only) when the user turns on location sharing. If denied, the app explains the fallback (the saved Kerrville area) and links to Settings. No background location and no push notifications.

## Future backend (SpaceTimeDB)

Replace one boundary: **`FloodWatchRepository`** in `src/data/repository.ts`.

1. Implement the interface in a new adapter (e.g. `src/data/spacetimeRepository.ts`). Map backend records to `src/domain/types.ts` and emit through `subscribe`/`getSnapshot`.
2. Return it from `createRepository()` in `src/data/RepositoryProvider.tsx` (or pass it via the provider's `repository` prop).

Screens only use `useAppState()` and `useRepository()`, so no screen changes should be needed. The pure reducer can keep handling local-only state (read flags, preferences) or be retired if the backend owns those.

## Limitations

- Demo data only: one persona (Dana Whitfield), one emergency contact (Maria Whitfield), one trip, Kerrville, TX.
- Verified on iOS simulators (iPhone 17, iPhone 16e) in Expo Go. No Android emulator was available, so Android layout and Google Maps have not been run.
- Spoken alerts use the device TTS (`expo-speech`). Audio output wasn't checked by ear; the call path is covered by tests.
