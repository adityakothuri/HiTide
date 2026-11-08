# Handoff: State Farm Flood Watch (as of Sat Nov 7, ~8 PM CT)

Deadline: **Sun Nov 8, 12:00 PM CT**. Feature freeze at 9 AM. Tracks: State Farm ("The Worst Day, at Scale") and Photon.

## The idea in 30 seconds
Most flood deaths happen in vehicles. Flood Watch protects opted-in State Farm drivers in a flash flood:
1. **Pre-trip:** if your usual route crosses a flooded road, you get a text with a safer route. A teen's parent gets a copy.
2. **En route:** the app speaks "Flooded road ahead. Turn around." and reroutes. Moving drivers never get texts.
3. **Stopped in water:** Flood Watch calls the driver, then their emergency contact, flags responders, and sends a drone. Its vision reports the water level and people on the car.

Demo town: Kerrville, TX (Guadalupe River). Roads come from OpenStreetMap and elevation from USGS, cached offline.

## Branches (all pushed)
| Branch | What | Worktree on Aditya's Mac |
|---|---|---|
| `feat/backend-sim` | Backend, sim, outreach, Photon sidecar, vault, docs. **The main work.** | `~/hackUTD` |
| `feat/frontend` | React driver app view + ops dashboard (snapshot). Branched before the latest backend commits, so merge `feat/backend-sim` into it. | `~/hackUTD-frontend` |
| `main` | Only the initial repo setup. Nothing has been merged yet. | |

## Run it
```bash
git fetch && git checkout feat/backend-sim
cp .env.example .env              # ask Aditya for the values (never commit .env)
cd backend && uv sync && uv run uvicorn app.main:app --reload      # http://localhost:8000/docs
uv run pytest -q                  # 200 tests, ~90% coverage
curl -X POST localhost:8000/api/demo/start                         # scripted 90 s demo
cd ../photon-sidecar && npm install && npm start                   # real iMessage (Photon Stable)
```
Without creds, everything runs in **mock mode**: outreach is logged and shown in the UI, but nothing is sent.

## What works (verified)
- **Data layer:** 4,234 Kerrville road segments, the real river line, a 10 m elevation model, and a flood sim calibrated against real elevations, with bridge elevations taken from their approach roads. Live NWS, USGS gauge (new OGC API) and USGS flood-impact feeds, with cached fallback.
- **Stages 1–3:** the full 7-step demo runs end to end in about 62 s (`POST /api/demo/start`). The case goes calling → family (+12 s) → drone (+18 s) → handed to responders.
- **Drone vision:** YOLOv8n on licensed real flood photos. A real "person on roof" detection (0.74) with water at the windows gives "boat required". The night thermal frame is clearly labelled simulated.
- **Photon (Stable) on real phones:** pre-trip text, the teen's parent copy, the emergency-contact text, the "Are you okay?" poll, and a **reply "safe" that closes the case**. CHECKPOINTS 2 and 3 passed.
- **Security and privacy:** ECC security-reviewer and AgentShield scans are done, and all high findings are fixed. No exact age or contact names reach any screen. Locations are shared only during an active warning. A same-origin guard covers the WebSocket and POSTs. Phone numbers never appear in logs or events.

## In progress right now
**Moving to Photon 2.0 + voice.** The Photon prize **requires Photon 2.0 (beta)**, and we built on Stable. Three agents are building:
- **A:** `outreach/photon2.py` sender, `PHOTON_MODE=mock|stable|photon2`, enroll script
- **B:** inbound replies over Photon 2.0's Socket.IO WebSocket (no tunnel needed)
- **C:** voice calls through ElevenLabs that use the driver's name, street and depth, plus "remembers the call": the transcript goes on the case and a follow-up iMessage is sent

Stable stays as the fallback until 2.0 is confirmed on a real phone.

**Dashboard setup still needed** (Aditya is doing this):
- **Photon 2.0** at app.beta.photon.codes:
  - Create a project (`pho_prj_…`) and an API key.
  - Turn on iMessage and add an SMS number.
  - Create a voice profile with outbound SIP enabled.
- **ElevenLabs:**
  - Create an agent and import the SMS number as a SIP trunk.
  - Collect the API key, agent ID and phone number ID.

## Where to look
| Need | File |
|---|---|
| API for the frontend (REST + WS events, privacy behaviour) | `docs/api-contract.md` |
| Status per phase, decisions, experiments | `vault/00 Home.md`, `vault/Decisions.md`, `vault/Experiments/` |
| Demo steps | `vault/Demo Script.md` |
| Privacy rules + security scan results | `vault/Privacy and Consent.md` |
| Tests and TDD evidence | `vault/TDD Evidence.md` |
| ECC (Everything Claude Code) usage | `vault/Tooling.md` |
| Photon setup scripts (Stable) | `photon-sidecar/` (`enroll.mjs`, `team.mjs`) |

## Env vars (values are in Aditya's `.env`, never in git)
`PHOTON_MODE`, `SPECTRUM_PROJECT_ID`, `SPECTRUM_PROJECT_SECRET`, `SPECTRUM_LINE`, `SIDECAR_KEY`, `DEMO_PHONE_A/B/C`, `SIM_PROFILE`, plus soon `PHOTON2_*` and `ELEVENLABS_*`. See `.env.example`.

Demo roles: **A** = pre-trip driver and teen's parent (gets 2 texts). **B** = en-route driver (alert plays in-app only, by design). **C** = Margaret's daughter (text + poll/call, replies "safe"). All three are enrolled on the Photon Stable line. B and C have each texted their assigned line once.

## Open items / where a colleague can help
1. **Frontend:** merge `feat/backend-sim` into `feat/frontend` and wire it to the live WS. The demo must show the "Turn around" TTS, the case timeline, drone images and counters. Label simulated parts (contract lists them).
2. **Pitch:** `vault/Pitch.md`. Source the average vehicle flood claim; the $15k in `backend/config/weights.yaml` is a placeholder.
3. **Backup video** of a full demo run.
4. **Merge to `main`** before submission, once the frontend is wired.
5. Known accepted risks: `/api/cases/{id}/reply` has no auth on the LAN, there's no rate limiting, and the vision images are elevated or ground shots rather than true top-down drone frames.
