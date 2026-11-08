# HiTide — consumer app (Expo)

React Native + Expo (SDK 58) + TypeScript app for people traveling through flood-prone areas. It covers the overview, route planning, updates, the turn-around voice alert, the safety check-in, support status, and profile/preferences. It runs in two modes. **Live mode** follows the HiTide backend's per-user danger assessment for one person (Dana Whitfield, `hc-dana`). **Sample-data mode** uses local fixtures and needs no backend.

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

## Presentation table (judges)

**One command**, from `mobile/`:

```bash
npm run present              # iOS Simulator on this Mac (recommended: no Wi-Fi needed between devices)
npm run present -- --phone   # real phones with Expo Go on the same Wi-Fi
npm run present -- --sample  # no backend at all: sample data (fallback if anything breaks)
```

It reuses the backend on :8000 if it's current (and refuses a stale one), or starts its own with mock outreach. It brings the July 4, 2025 replay to the Kerrville crest (about a minute), boots or creates an iPhone simulator, and starts Expo. Press **i** to open the app. Opening through **i** also hides Expo Go's floating gear button.


**New on the table (Nov 8, late morning)**

- **Flood map.** Every map now shows the dashboard's flood layers for Kerrville:
  - flooded roads: thick red
  - likely flooded roads: thin translucent amber
  - roads not checked: faint grey
  - crossings with water, as dots
  - river gauges by NWS category, as diamonds
  The Home map has a **Flood map** button that opens the full map, with a legend, counts and active alerts.
- **Choose a route.** Trips lists up to 3 ways from home to work (`GET /api/routes/options`). Each shows its distance, time, main roads and flooding in words. "Fastest" may cross water and says so. Choosing a route sends it to the backend's pre-trip check.
- **Way to higher ground.** The check-in and help screens draw a dark route line and a directions card (`GET /api/users/{id}/directions`), e.g. "Leave Park Street and head for higher ground by G Street, then Travis Street…".
- **Talk to the HiTide assistant.** This is the link under "I need help" on check-in, and the main button on the help screen. It dials the team's ElevenLabs + Photon assistant number after the backend loads Dana's street, water depth and directions into the agent.
  - On a real iPhone, the dialer opens.
  - On the simulator, a sheet shows the number to dial from any phone.
  - A "need help" in that call flags responders on the dashboard. Nothing dials 911.
  - Setup: `docs/voice-agent.md` §8 (paste the prompt and add the variables in ElevenLabs), then add `HITIDE_ASSISTANT_LIVE=1` to the backend `.env`. Without that flag the button works end to end, but the call is simulated.

**The 60-second walkthrough**

1. Home shows **Live · July 4, 2025 replay** and the Flash Flood Emergency. That is the same backend the dashboard shows.
2. Long-press the **HiTide** mark (or Profile → Developer), then tap **Reset demo** and wait for "Preparing…" to finish (about 1 min).
3. Tap **Start**. The phone drives Dana's usual route, and the backend decides what happens:
   - **Turn around** (spoken aloud).
   - Then, stopped on Park Street, **Are you safe?**
4. Tap **I need help**. The support timeline fills from the backend. The dashboard's at-risk list shows Dana as critical with "needs help".
5. Between judges: **Reset demo**.

Reset demo and `npm run present` restart the shared replay, so they restart the dashboard's replay too. Use `--keep-replay` if the dashboard is mid-story.

**If something goes wrong**

| Symptom | Fix |
|---|---|
| Badge says Offline or "Can't check for flooding" | Backend down. Rerun `npm run present`. The app is behaving correctly: it never shows "clear" when it can't check. |
| Badge says Connecting… | Backend up, replay not started. Tap **Reset demo**. |
| App doesn't match the code you just changed | Metro served a stale bundle. Stop it and run `npx expo start --clear`. |
| Phone can't load the app | Venue Wi-Fi blocks phone-to-laptop traffic. Use the simulator, or `--sample`. |
| Expo Go shows a gear button | Reopen with `i` from Expo, or open `exp://127.0.0.1:8081?__expo_disable_fab=1`. |
| Anything else, 2 minutes before judging | `npm run present -- --sample`. Every screen works on sample data. |

Native screenshots (iPhone 17 Pro simulator, Expo Go, Apple Maps): `docs/screenshots/native-02-turn-around.png`, `native-03-check-in.png`, `native-04-support.png`.

## Live mode (backend)

The app reads the same per-user danger pipeline the operations dashboard shows (`docs/api-contract.md`, "Per-user danger").

```bash
# 1. Backend (repo root). Offline test data; outreach stays mock.
./dev.sh                                  # or: cd backend && uv run uvicorn app.main:app --port 8000
curl -X POST "localhost:8000/api/demo/start?scenario=hill_country"   # start the July 4, 2025 replay

# 2. App
cd mobile
cp .env.example .env.local                # EXPO_PUBLIC_API_URL=http://localhost:8000, EXPO_PUBLIC_USER_ID=hc-dana
npx expo start                            # i = iOS simulator, w = web preview
```

On a phone with Expo Go, set `EXPO_PUBLIC_API_URL` to this Mac's LAN IP, and start the backend with `--host 0.0.0.0`.

What happens:

- **Reads.** `GET /api/users/hc-dana/danger` runs on launch and every 5 s. A WebSocket `user.danger` event for this user triggers an immediate refetch. `GET /api/safety/summary` (replay or live) and `GET /api/region/gauges` (the Kerrville gauge card) run every 30 s. Every payload is validated with zod (`src/data/live/schema.ts`). An invalid payload is rejected whole, never half-applied, and the badge switches to Offline, so a stale picture is never labelled Live.
- **Mapping.** `src/data/live/mapAssessment.ts` is a pure function with its own tests:
  - `warning`+ shows the NWS warning.
  - A flooded road ahead or on the planned route becomes the closure.
  - `turn_around` while driving shows the turn-around screen once per flooded road.
  - `awaiting_reply` or `case_open` opens the check-in.
  - `need_help` shows the support status, whose timeline is built from the backend's own events.
  - Unknown depth is shown as "depth not measured". Times the source didn't give are left blank.
- **Writes.**
  - "I'm safe" and "I need help" call `POST /reply`. Help is single-flight.
  - Choosing a route calls `POST /route`, the backend's pre-trip check of every road on it. The planned route is also checked on launch.
  - Contact edits and preferences stay on the phone.
- **Unknown is never clear.** If the backend can't be reached, or its evidence is degraded or low-confidence, Home says so ("Can't check for flooding right now" or "Some flood data is unavailable") instead of "No flood warnings".
- **Header badge.** It shows "Live · July 4, 2025 replay · 7:05 AM", "Connecting…" (backend up, replay not started), "Offline · last update …", or "Sample data".
- **Demo drive.** Long-press the HiTide mark, or go to Profile → Developer, then press **Start** under Demo drive.
  - The app sends location pings along Dana's usual route, every 1.5 s, and stops on Park Street at Quinlan Creek.
  - The backend decides everything that follows: the turn-around alert, then the stopped-in-water check-in.
  - Run it once the replay reaches the Kerrville crest (after about 06:40 CDT on the replay clock). Earlier, the backend correctly raises nothing on that road.
  - A finished episode stays on the backend until the replay restarts. Restart it with the `demo/start` call above to run the drive again.
  - For a quick, repeatable demo, use `curl -X POST "localhost:8000/api/demo/start?scenario=hill_country&speed=1000"`. It reaches the crest in about a minute, then holds the final flooded state.
  - Screenshots of the live flow are in `docs/screenshots/live-01-home.png` through `live-05-offline.png`.
- **Scenario tiles** still jump to every reference state. In live mode they pause backend updates until **Reset**.

## Scenario controls (development only)

Every reference state can be reached immediately:

- **Long-press the HiTide mark** in any header, or use **Profile → Developer: scenario controls**. Choose Normal, Flood warning, Alternate route, Turn-around, Check-in, Help requested, Resolved, or Reset. A toggle simulates network write failures.
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

## Backend boundary

One boundary, **`HiTideRepository`** in `src/data/repository.ts`, has two implementations:

- `MockHiTideRepository`: sample data.
- `LiveHiTideRepository` (`src/data/live/`): the FastAPI backend. When the backend runs on SpacetimeDB (see `vault/Modules/SpacetimeDB.md`), the phone reads that state through the API.

Both share `src/data/store.ts` (reducer, subscribe, persistence). `RepositoryProvider` chooses live when `EXPO_PUBLIC_API_URL` is set.

To talk to SpacetimeDB directly instead:

1. Implement the interface in a new adapter (e.g. `src/data/spacetimeRepository.ts`). Map backend records to `src/domain/types.ts` and emit through `subscribe`/`getSnapshot`.
2. Return it from `createRepository()` in `src/data/RepositoryProvider.tsx` (or pass it via the provider's `repository` prop).

Screens only use `useAppState()` and `useRepository()`, so no screen changes should be needed. The pure reducer can keep handling local-only state (read flags, preferences) or be retired if the backend owns those.

## Polish pass (Nov 8)

- Identity: independent HiTide only (no insurer, policy or claims content anywhere). Accent stays cobalt `#2448E8`, the same value as the ops dashboard. White text on it measures 6.6:1. Secondary slate text darkened to `#626D85` (5.2:1 on white, 4.9:1 on surface) to meet WCAG AA.
- Type: eyebrows and section labels ("Voice alert", "Route update", "Emergency contact", ...) are now sentence case with normal tracking. Screens no longer use ad-hoc font sizes; they use tokens (`font.alert`, `largeTitle`, `tabLabel`, `wordmark`, `buttonLarge` were added).
- Tab bar is taller so labels are never clipped. Turn-around tightens on short screens (iPhone SE size) so the action and the voice status stay visible. Switches keep the on-brand thumb on web. The developer link has a 44 pt target.
- Verified with Expo web plus Playwright at 390×844 and 375×667 (`docs/screenshots/polish-*.png`). No iOS simulator was available on the machine used for this pass.

## Limitations

- One persona (Dana Whitfield), one emergency contact (Maria Whitfield), one trip, Kerrville, TX. In live mode, flood conditions come from the backend (July 4, 2025 replay or live Texas feeds). Route geometry, the trip and the persona remain demo fixtures.
- In live mode the app doesn't send real GPS. Location comes only from the developer demo drive, because a real phone outside Kerrville would sit outside the replay region.
- The phone sends no API key. The backend's write endpoints accept it because native apps send no Origin header. Set `SAFETY_API_KEY` and keep the backend on a trusted LAN for demos. See `docs/api-contract.md`.
- Verified on iOS simulators (iPhone 17, iPhone 16e; live mode on iPhone 17 Pro, iOS 26.5) in Expo Go. No Android emulator was available, so Android layout and Google Maps have not been run.
- Spoken alerts use the device TTS (`expo-speech`). Audio output wasn't checked by ear; the call path is covered by tests.
