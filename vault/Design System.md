---
tags: [floodwatch, frontend, design]
status: checkpoint-1
updated: 2026-11-07
---

# Design System

The frontend has two surfaces: the **driver app**, a screen inside an insurer's existing phone app, and the **operations console**, used by the catastrophe team and responders. It should read as calm, plain-spoken, and precise. Boldness gets spent in exactly two places: the console map and the "minutes gained" number.

> [!note] Direction
> - **Purpose:** keep a driver out of floodwater, and get help to them fast if they're already in it.
> - **Audience:** a scared driver at arm's length from a phone, and a cat-team operator scanning 20 cases on a projector.
> - **Tone:** a utility from a large insurer. Plain words, white space, one red.
> - **Memorable detail:** the roads themselves carry the water scale. The map is the only saturated thing on the screen, so the flood is the loudest element.

## 1. Color tokens

Defined once in `frontend/src/styles/tokens.css`. Components only reference `var(--…)`, and a stylelint rule fails on any hex value outside the tokens file.

### Brand and text

| Token | Value | Use |
|---|---|---|
| `--brand-red` | `#B3121F` | Wordmark, primary button fill, selected tab/filter indicator. **Never** used for danger. |
| `--ink` | `#24272B` | Body and heading text |
| `--neutral-1` | `#F0F2F4` | Hover fill, skeleton base |
| `--neutral-2` | `#DDE1E5` | Borders, dividers |
| `--neutral-3` | `#BCC3CA` | Disabled borders, map open roads |
| `--neutral-4` | `#838C95` | Icons and waiting-state marks only (not text) |
| `--neutral-5` | `#5F6870` | Secondary text |
| `--neutral-6` | `#3E454C` | Strong secondary text, map labels |
| `--surface` | `#FFFFFF` | Cards, panels, phone screens |
| `--surface-page` | `#F4F6F8` | Page background (cool gray-white) |

### Water scale (flood depth on maps and segments)

| Token | Value | Road status | Depth |
|---|---|---|---|
| `--water-1` | `#DCEBF7` | (river fill, warning polygon fill) | n/a |
| `--water-2` | `#A9CDEB` | `caution` | 3–6 in |
| `--water-3` | `#5E9ED6` | `closed` | ≥ 6 in |
| `--water-4` | `#2366A8` | `float` | ≥ 12 in |
| `--water-5` | `#0B2D52` | `boat` | ≥ 24 in, heavier stroke |

`open` roads are drawn in `--neutral-3`. The water scale is never the only signal: the case card and road tooltip also give the depth in inches and the status word.

### Status (distinct from brand-red)

| Token | Text | Background | Icon (Lucide) | Label |
|---|---|---|---|---|
| safe | `--safe #1E6B3A` | `--safe-bg #E6F2EA` | `ShieldCheck` | "Safe" |
| caution | `--caution #7A4F00` | `--caution-bg #FFF1D1` | `TriangleAlert` | "Caution" |

`--caution-mark #B07800` (3.80:1) is for caution map markers and icons only, never text.
| critical | `--critical #931566` | `--critical-bg #FBE9F3` | `OctagonAlert` | "Critical" |
| info | `--info #3A5A82` | `--info-bg #E8EEF6` | `Info` | "Info" |

The critical takeover uses `--critical-deep #7A0F46` as a fill with white text.

**Rule:** brand-red never communicates danger. Danger is always shown as icon + label + the critical color. Brand red has hue 355°, critical 321°. On screen, critical reads as magenta-plum and brand reads as red.

### Contrast (WCAG 2.x, computed by `frontend/scripts/contrast.mjs`)

| Pair | Ratio | AA normal (4.5) |
|---|---|---|
| ink on surface | 15.00 | pass |
| ink on surface-page | 13.84 | pass |
| neutral-5 on surface | 5.67 | pass |
| neutral-5 on surface-page | 5.24 | pass |
| neutral-6 on surface | 9.72 | pass |
| white on brand-red | 6.95 | pass |
| brand-red on surface-page | 6.41 | pass |
| safe on surface / on safe-bg | 6.52 / 5.67 | pass |
| caution on surface / on caution-bg | 7.13 / 6.37 | pass |
| critical on surface / on critical-bg | 8.27 / 7.11 | pass |
| white on critical-deep | 10.58 | pass |
| info on surface / on info-bg | 7.08 / 6.07 | pass |
| ink on water-1 / water-2 | 12.33 / 9.01 | pass |
| white on water-4 / water-5 | 5.94 / 13.89 | pass |
| neutral-4 on surface / surface-page | 3.41 / 3.15 | **fails for text**. Icons only, which need 3:1 (passes) |
| caution-mark on surface | 3.80 | markers only (3:1) |
| focus ring: info on surface / white ring on critical-deep | 7.08 / 10.58 | dark surfaces use the white `--focus-ring-on-dark` |
| water-3 on surface-page | 2.64 | map line only, never text. Always paired with the status word in the tooltip |

## 2. Typography

- **Public Sans** for everything, self-hosted via `@fontsource/public-sans` (works offline). It was designed for US government services: legible at small sizes, sturdy on a projector, and it sounds institutional without being cold. Not Inter.
- Weights: 400, 600, 700.
- Sentence case everywhere. No all-caps, no letter-spacing, no eyebrow text.
- `.num` utility: `font-variant-numeric: tabular-nums` for ETAs, counts, depths, times.

| Step | Size / line | Weight | Use |
|---|---|---|---|
| `--text-xs` | 13 / 18 | 400 | Timestamps, footnotes, meta |
| `--text-sm` | 15 / 22 | 400/600 | Console body, queue rows, labels |
| `--text-md` | 17 / 26 | 400/600 | Driver body, buttons |
| `--text-lg` | 22 / 28 | 600 | Card titles, panel headings |
| `--text-xl` | 30 / 36 | 700 | Screen titles, counters |
| `--text-2xl` | 44 / 50 | 700 | Turn-around headline, minutes gained |

## 3. Shape, depth, spacing

- **Spacing:** 8px grid (`--space-1` = 4 for hairline gaps only, then 8, 16, 24, 32, 48, 64).
- **Radius:**
  - `--radius-sm` 4px: inputs, chips, badges, tabs
  - `--radius-md` 8px: cards, buttons, panels
  - `--radius-lg` 16px: phone bottom sheets and the phone frame only
- **Depth:** one token, `--shadow-float: 0 4px 16px rgb(36 39 43 / 0.12)`, for sheets, popovers, toasts and the demo dialog. Console cards use a 1px `--neutral-2` border and no shadow.
- **Focus:** a 2px `--info` outline with a 2px offset on every interactive element (`:focus-visible`). On dark fills (`.on-dark`), the ring is white. Brand-red isn't used for focus because it would read as "selected".
- **Touch:** minimum 44×44 in the driver app. Primary driver buttons are 56px tall.

## 4. Motion

- **One orchestrated moment:** a newly stalled case slides into the top of the queue (220ms translate + height), and the map `flyTo`s the car (1.2s).
- The drone marker is interpolated along its reported positions with requestAnimationFrame, and a trail line grows behind it.
- That's all. No page fades, no hover lift, no animated gradients.
- `prefers-reduced-motion: reduce` turns both into instant position changes and a `jumpTo`.

## 5. Wireframes

### Driver app (390×844, phone frame)

Every screen has a top bar (wordmark) and a bottom tab bar (Home, Trips, Claims, Profile; only Home works).

**5.1 Home, calm**
```
┌──────────────────────────────────────┐
│ ■ State Farm Flood Watch        (gear)│
├──────────────────────────────────────┤
│ Good evening, Margaret               │
│                                      │
│ ┌──────────────────────────────────┐ │
│ │ (shield) Flood Watch is on       │ │
│ │ No flood warnings near you.      │ │
│ │ Checked 2 min ago                │ │
│ └──────────────────────────────────┘ │
│                                      │
│ Next trip                            │
│ ┌──────────────────────────────────┐ │
│ │ Church, usually 7:30 PM          │ │
│ │ Home to Notre Dame Catholic Ch.  │ │
│ │ 2.9 miles, about 9 minutes       │ │
│ │ No flooding on this route        │ │
│ └──────────────────────────────────┘ │
│                                      │
│ Emergency contacts                   │
│ ┌──────────────────────────────────┐ │
│ │ Maria Hale, daughter       Set up│ │
│ └──────────────────────────────────┘ │
│                                      │
│ Concept prototype. Not an official…  │
├──────────────────────────────────────┤
│ [Home]   Trips    Claims   Profile   │
└──────────────────────────────────────┘
```

**5.2 Warning active**
```
┌──────────────────────────────────────┐
│ ■ State Farm Flood Watch             │
├──────────────────────────────────────┤
│▌(!) Flash flood warning              │  caution banner, left rule
│▌ Kerr County until 2:15 AM           │
│▌ Simulated warning for this demo     │
│                                      │
│ Your usual route to church crosses   │
│ a flooded road                       │
│ ┌──────────────────────────────────┐ │
│ │ [ mini map: route gray,          │ │
│ │   flooded segment water-4,       │ │
│ │   safer route ink dashed→solid ] │ │
│ │──────────────────────────────────│ │
│ │ Water St at Guadalupe River      │ │
│ │ About 14 in of water             │ │
│ │ Safer route adds 4 minutes       │ │
│ └──────────────────────────────────┘ │
│ ┌──────────────────────────────────┐ │
│ │        Use safer route           │ │  primary, brand-red, 56px
│ └──────────────────────────────────┘ │
│        Remind me later               │  secondary, text button
├──────────────────────────────────────┤
│ [Home]   Trips    Claims   Profile   │
└──────────────────────────────────────┘
```
After tapping: the button becomes "Using safer route" (disabled, check icon), and the card's map shows only the safer route.

**5.3 En route alert (full-screen takeover, critical-deep fill)**
```
┌──────────────────────────────────────┐
│                                      │
│   (octagon-alert, 64px, white)       │
│                                      │
│   Flooded road ahead.                │  44px bold, white
│   Turn around.                       │
│                                      │
│   Water St, 600 ft ahead             │  22px
│   About 14 in of water               │
│                                      │
│   (speaker) Speaking this alert      │  13px, mutes on tap
│                                      │
│                                      │
│ ┌──────────────────────────────────┐ │
│ │         Show new route           │ │  white button, ink text, 64px
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```
The tab bar is hidden while the takeover shows. `role="alertdialog"`, and focus goes to the action.

**5.4 Check-in**
```
┌──────────────────────────────────────┐
│ ■ State Farm Flood Watch             │
├──────────────────────────────────────┤
│ Your car stopped on a flooded road   │
│ Water St, 8:42 PM                    │
│                                      │
│ Are you safe?                        │
│ ┌──────────────────────────────────┐ │
│ │ (shield-check)  I'm safe         │ │  72px, safe outline
│ └──────────────────────────────────┘ │
│ ┌──────────────────────────────────┐ │
│ │ (hand)  I need help              │ │  72px, critical outline
│ └──────────────────────────────────┘ │
│                                      │
│ If you're in danger right now        │
│ ┌──────────────────────────────────┐ │
│ │ (phone)  Call 911                │ │  separate group, ink fill
│ └──────────────────────────────────┘ │
│ We'll keep trying to reach you and   │
│ Maria if we don't hear back.         │
└──────────────────────────────────────┘
```

**5.5 Help is on the way**
```
┌──────────────────────────────────────┐
│ ■ State Farm Flood Watch             │
├──────────────────────────────────────┤
│ Help is on the way                   │
│ Stay on the roof if water is rising. │
│ A life jacket will be dropped next   │
│ to you.                              │
│                                      │
│ ● 8:42 PM  We called you        Done │
│ │                                    │
│ ● 8:43 PM  We contacted Maria   Done │
│ │          (emergency contact)       │
│ ◐ 8:43 PM  Drone on the way          │
│ │          Arriving in 2 min  In prog│
│ ○          Rescue team notified      │
│                              Waiting │
│                                      │
│ ┌──────────────────────────────────┐ │
│ │ (phone)  Call 911                │ │
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```
Step states are shown by icon shape (filled check / half ring / empty ring) **and** a text label, never by color alone.

**5.6 After: claim started**
```
┌──────────────────────────────────────┐
│ ■ State Farm Flood Watch             │
├──────────────────────────────────────┤
│ You're safe. We started your claim.  │
│                                      │
│ ┌──────────────────────────────────┐ │
│ │ Auto claim 31-8842-K17           │ │
│ │ 2019 Toyota Camry                │ │
│ │ Status: Started, no action needed│ │
│ └──────────────────────────────────┘ │
│ Next steps                           │
│ (truck)  Tow to Kerrville Collision  │
│          Scheduled, tomorrow 8 AM    │
│ (car)    Rental car                  │
│          Ready at Enterprise, Sidney │
│          Baker St                    │
│ (doc)    Photos from the drone are   │
│          attached to your claim      │
│                                      │
│ [ View claim ]  (secondary)          │
└──────────────────────────────────────┘
```

**5.7 Settings (gear icon on Home)**
```
┌──────────────────────────────────────┐
│ ← Flood Watch settings               │
├──────────────────────────────────────┤
│ Flood Watch                    [on ] │  switch
│ We check your usual routes against   │
│ National Weather Service and USGS    │
│ flood data.                          │
│                                      │
│ Location                             │
│ We use your location only while a    │
│ flood warning is active near you.    │
│                                      │
│ Spoken alerts                  [on ] │
│ [ Test spoken alert ] (unlocks audio)│
│                                      │
│ Emergency contacts                   │
│ Maria Hale, daughter                 │
│ (830) 555-0142               Edit    │
│ + Add contact                        │
└──────────────────────────────────────┘
```

### Operations console (1440×900)

```
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│ ■ State Farm Flood Watch   Flash flood warning, Kerr County (simulated)                       │
│  Warned 42   Rerouted 17   Stopped in water 3   Confirmed safe 9      NWS 8:41 PM  USGS 8:40 PM│
├─────────────────────┬────────────────────────────────────────────────┬────────────────────────┤
│ Cases               │                                                │ (!) Critical           │
│ [Critical 2][Contac │                                                │ Margaret, 75+          │
│ ting 1][Drone 1][Res│                 MAP                            │ 2019 Toyota Camry      │
│ olved 9]            │   muted surface, river water-1,                │ Water St at Guadalupe  │
│─────────────────────│   roads neutral-3, flooded roads water-2..5    │────────────────────────│
│(!) Critical         │   warning polygon outlined info                │ Drone                  │
│ Margaret, 75+       │   cars: circle + status glyph                  │  Minutes gained        │
│ Water St     4 min  │   drone: heading arrow + trail                 │  14                    │  2xl, water-5
│ Drone en route      │                                                │  Drone 2 min  Crew 16  │
│─────────────────────│                                                │ [Speak] [Drop jacket]  │
│(!) Critical         │                                                │ [Return]               │
│ Luis, 35–49         │                                                │────────────────────────│
│ Junction Hwy 9 min  │                                                │ Timeline               │
│ Contacting family   │                                                │ 8:42 Car stopped …     │
│─────────────────────│                                                │ 8:42 Call to driver,   │
│(△) Caution          │                                                │      no answer (mock)  │
│ Dana, 25–34  …      │                                                │ 8:43 Text to Maria,    │
│                     │                     [legend: depth scale]      │      read, replied …   │
│                     │                                                │────────────────────────│
│                     │                                                │ For responders         │
│                     │                                                │ 30.043, -99.131        │
│                     │                                                │ 1 person, on roof      │
│                     │                                                │ 20 in, boat required   │
├─────────────────────┴────────────────────────────────────────────────┴────────────────────────┤
│ Concept prototype. Not an official State Farm product.                 (dot) Offline demo data │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```
- Queue: 360px. Detail: 420px. Map: the rest. At 1280px wide the map shrinks to 500px.
- The detail column scrolls on its own. The drone panel only appears when a drone is assigned.
- **Empty detail:** "Select a case from the queue to see its timeline and drone status."
- **Empty queue:** "No cars are stopped in water. Cases appear here when a trip stops on a flooded road."

### Presentation mode (`/present`)
Phone frame (390×844, scaled to fit the height) on the left, the console on the right. Both run from one store. `Shift+D` opens the demo panel: Run scenario, Next step, Reset. The current step is shown as a caption.

## 6. Anti-template review of this plan

Checked against brief §9 and the `frontend-design-direction` anti-patterns.

| Looked generic | Revised to |
|---|---|
| Four KPI counter cards in a row with icons | Inline counters in the top bar: a number plus a plain label, no cards and no icons |
| Every panel a rounded shadow card | Console uses bordered sections divided by rules. Shadow only on floating layers |
| Red "Critical" pills on queue rows (would reuse brand-red) | Critical color + `OctagonAlert` icon + the word |
| Map on a dark basemap with glowing markers | Light neutral surface with no basemap tiles. Roads carry the water scale |
| Help timeline with colored dots only | Icon shape + text state on every step |
| Meta strings like "2.9 mi · 9 min" | Written out: "2.9 miles, about 9 minutes" |
| "Minutes gained" with a gradient hero number | Plain 44px tabular numeral in water-5, with a one-line explanation under it |
| Uppercase section labels ("CASES", "TIMELINE") | Sentence-case headings at `--text-sm` 600 |
| Hero greeting illustration on Home | Removed. Text greeting only |

## 7. Content states (every component)

| State | Treatment |
|---|---|
| Loading | Skeletons shaped like the real rows, cards and map (`--neutral-1` blocks; no shimmer under reduced motion) |
| Empty | An instruction (see the console empties above) |
| Error | What failed + Retry. E.g. "Couldn't load road data. Check that the backend is running, then retry." |
| Stale | The last-updated time turns caution color with a `Clock` icon and "Updated 6 min ago" once data is more than 5 minutes old |
| Offline demo | A persistent chip in the footer: "Offline demo data" |

## Related

- [[Dashboard]], [[Driver App]], [[Decisions]], [[Tooling]]

## 8. Round 2: aligned to State Farm's public design system (2026-11-07)

Values taken from statefarm.com's `1x.core.css` (DXL "oneX") and applied to `frontend/src/styles/tokens.css`. These supersede the color values in section 1 where they differ.

| Token | Value | Source use |
|---|---|---|
| `--brand-red` | `#D62311` | `.-oneX-btn-primary` |
| `--brand-red-hover` / `-active` | `#A11B13` / `#701611` | primary hover / active |
| `--ink` / `--ink-strong` | `#403C3C` / `#212121` | headings, body |
| `--surface-page`, `--neutral-1` | `#F4F3F3` | page background |
| `--neutral-2` | `#E4E3E3` | header and tab rules |
| `--info` (links, focus ring) | `#0073A8` | `:focus` outline 2px, offset 2px |

- **Type:** Mecherle Sans is proprietary, so the stand-in is Source Sans 3 (another humanist sans). Headings are weight 600; body text is 16px.
- **Buttons:** pill shaped. Primary is solid red. Secondary is white with a red border and red text. Text links are blue.
- **Patterns:**
  - Headers are white with a 1px bottom rule, and tabs use an underline.
  - Notifications are white with a colored left rule.
  - Lists are white groups of rows with red chevrons.
- **Unchanged:** the critical color stays magenta-crimson (never brand red), and the water scale is the same. All contrast pairs still pass (`npm run contrast`).

## 9. Round 3: dispatch console and native phone (2026-11-07)

User feedback: the UI still "looks like vibecode". Directions the user chose:
- **Console:** a dark, map-first dispatch command center.
- **Phone:** a native iOS feel.
- **Map:** a real basemap from an existing maps API.

Skills used:
- Anthropic `frontend-design`, installed in `.claude/skills/`.
- Vercel `web-design-guidelines`, installed in `.claude/skills/` with the guidelines cached.
- The local `taste` and `make-interfaces-feel-better`.

**Basemap:** CARTO GL vector styles (no key, OpenStreetMap data). The console uses dark-matter and the phone uses voyager. `src/map/` tunes the style (POIs and house numbers hidden, water tinted) and draws our flood layers under the street labels. If the style doesn't load within 4 s, or tiles keep failing, it falls back to the bundled town data.

### Console tokens (`[data-theme='dispatch']`)

| Name | Hex | Role |
|---|---|---|
| Night | `#0E1620` | Map background, app base. Slate-navy from the basemap, deliberately not neutral black |
| Panel | `#141E29` | Floating panels |
| Raised | `#1B2734` | Rows, inputs, hover |
| Text / muted | `#E6EDF3` / `#97A6B5` | |
| Critical | `#F0569A` | Stopped cars, critical cases. Distinct from brand red |
| Water scale | `#9FDCFF` to `#A26BFF` | Cyan to violet, deeper means more violet. Glows on the dark map |
| Brand red | `#D62311` | Wordmark and primary actions only |

**Type:** IBM Plex Sans. It has an industrial, engineering voice that suits a dispatch tool, and it isn't the default Inter. Every changing number uses tabular figures.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ◇ State Farm Flood Watch  Flood operations │ Flash flood warning, Kerr Co │ 11 warned  2 rerouted  1 stopped  1 verified  $16,500 │ ● Live │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌Cases──────────┐   full-bleed dark street map                ┌Margaret Hale──────┐ │
│ │All Critical … │   flooded roads glow cyan→violet            │ Critical, 75+      │ │
│ │▌Margaret 75+  │        ◉ car (pulse)   ▲ drone + trail      │ 17 min gained      │ │
│ │ Riverside Dr  │                                             │ ▬▬▬ drone 0:15     │ │
│ │ ●●●●○○○ 4 min │                                             │ ▬▬▬▬▬▬▬▬▬ crew 17m │ │
│ └───────────────┘   [legend chip]                             │ actions, timeline  │ │
│                                                               └────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

**The one bold element:** "Minutes gained", drawn as a race between two bars (drone ETA against ground-crew ETA). Everything else stays quiet.

### Phone (iOS grouped)

- **Type:** system font (SF Pro on Apple devices). Large title 34/41, body 17/22, footnote 13/18.
- **Surfaces:** page `#F2F2F7`, white inset groups with a 10px radius and hairline separators inset 16px.
- **Home:** a red State Farm band behind the large title.
- **Controls:** filled red buttons, 50px tall with a 12px radius. Translucent tab bar.
- **Maps:** small MiniMaps (voyager style) on the warning, home trip and help screens.

### Anti-default review of this plan

| Default it could fall into | What we do instead |
|---|---|
| Near-black with one acid accent (`frontend-design` tell 2) | Slate-navy taken from the basemap, with multiple semantic hues: water scale, critical, safe, caution |
| Identical rounded cards everywhere (tell 4) | Two surfaces only (floating panels, raised rows). Detail sections are divided by spacing, not boxes |
| Pill soup of risk factors | Stacked list with icons |
| KPI tiles | Inline counters in the top bar |
| Generic iOS clone | State Farm red band, real map cards, and calls and notifications that mirror the backend's actual outreach |
