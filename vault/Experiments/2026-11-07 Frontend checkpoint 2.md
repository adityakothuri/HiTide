---
tags: [hitide, experiment, frontend]
updated: 2026-11-07
---

# Frontend checkpoint 2: tokens, primitives, data layer

**Screenshots:** `screenshots/cp2-gallery-1440x900.png`, `screenshots/cp2-gallery-390x844.png`

## Self-critique (as a skeptical insurer product designer)

- Banners shrank to fit their text, which looked like stray stickers. They're now full width.
- At 390 px the gallery had no side gutter. Added a 16 px minimum.
- Critical magenta against brand red is distinct at a glance on screen. Kept.
- Removed decoration: none was left to remove. Counters have no icons or cards, and sections have no shadows.

## Review findings fixed

- **`typescript-reviewer`** (1 critical, 5 high, all fixed):
  - The StrictMode remount leaked a WebSocket and caused a reconnect loop. Each handler now checks it owns the current socket.
  - A snapshot wiped driver history on every reconnect. Now only a sim reset (sim time goes backwards) clears it. Test-first, 75 tests.
  - Mock `nextStep` crashed at the end of the recording and replayed the snapshot. Its time offset was not re-anchored.
  - Drone "return" could fire with no drone.
- **`a11y-architect`** (3 high, all fixed):
  - The focus ring was invisible on dark fills. Added a white ring for `.on-dark`.
  - Timeline and banner state was hidden from screen readers. Added visually hidden status and tone labels.
  - Also fixed: faint control borders (now neutral-5), neutral-4 on the page background was 2.9:1 (darkened to 3.15:1), the toast dismiss target is now 44 px, loading has a status label, and there's a forced-colors rule for the selected tab.
- **Not done yet:** `Section` heading level prop, and toast `scroll-padding`.

## Data

The offline replay is a real recording of the backend's 7-step demo (232 events) at `frontend/src/demo/recording.json`. Recorded from a backend instance on :8001 in this worktree.
