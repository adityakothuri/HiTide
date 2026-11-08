---
date: 2026-11-07
tags: [floodwatch, experiment, photon]
changed: PHOTON_MODE=photon with real Spectrum creds; photon-sidecar running; 3 teammates enrolled on the shared line
result: CHECKPOINT 2 + 3 pass on a real phone (texts, poll, inbound reply); voice still pending ElevenLabs
---

# Photon live test

Related: [[Photon Outreach]], [[Stage 3 Stopped in water]], [[Decisions]]

**Setup findings:**
- A free Spectrum project has a **shared** iMessage line. Recipients must be **enrolled as project users** (`POST /projects/{id}/users {type: "shared", phoneNumber}`), and each one gets its own assigned line number. Adding a phone to your Photon account does *not* enroll it.
- Scripts: `photon-sidecar/enroll.mjs` (one person), `photon-sidecar/team.mjs` (sets `DEMO_PHONE_A/B/C` in `.env` and enrolls them).
- Photon's starter expects bun. With npm, run it as `npx tsx --env-file=.env src/index.ts`. Its env names are `PROJECT_ID`/`PROJECT_SECRET`, and the sidecar accepts either naming.
- Gotcha: a number entered without the `1` (`+972…`) enrolls as an Israeli number. `team.mjs` validates E.164 format, but it can't catch a missing country code.

**Run (single phone as A, B and C):**

| Step | Message | Mode | Result |
|---|---|---|---|
| 2 | Pre-trip warning to A | photon | delivered |
| 2 | Teen's parent copy to A | photon | delivered |
| 3 | "Turn around" to B | in-app TTS only (driver moving, no text) | correct |
| 5 | Emergency-contact text to C | photon | delivered |
| 5 | "Are you okay?" poll to C (voice fallback) | photon | delivered |
| reply | C replied "safe" → `/api/photon/inbound` 200 → case `resolved` | photon | works |

The sidecar logged 4 × `/send ok` and 1 × `/poll ok`, with no failures.

**Next:** voice via an ElevenLabs agent over SIP to the Photon line. It's unclear whether a free shared line supports outbound voice. Timebox: 2 h, with the poll as the fallback.
