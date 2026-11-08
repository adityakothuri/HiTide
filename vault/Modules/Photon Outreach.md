---
tags: [floodwatch, module, outreach, photon]
status: todo
updated: 2026-11-07
---

# Photon Outreach

Every outbound message goes through one adapter. It runs in `mock` mode until Photon creds exist, then switches to `photon`.

## Why Photon Spectrum (Stable)

Chosen 2026-11-07. See [[Decisions]]. Spectrum is the only version that documents polls, read receipts, and outbound SIP voice on an iMessage line.

## Adapter

- `outreach/base.py`: the `Outreach` protocol (`send_text`, `send_poll`, `place_call`)
- `outreach/mock.py`: logs and streams to the UI, sends nothing
- `outreach/photon_spectrum.py`: Spectrum REST API over `httpx` (Basic auth, OpenAPI at `/openapi/json`)
- `outreach/voice_elevenlabs.py`: ElevenLabs outbound call through a SIP trunk to `sip.spectrum.photon.codes:5061` (TLS)
- `outreach/log.py`: writes every attempt to `data/outreach_log.jsonl` and emits a WS `outreach` event

## Guards

- **Allowlist**: only numbers from `DEMO_PHONE_A/B/C` can be contacted. Everything else is mock-only.
- **Moving drivers**: no texts to a driver with `driver.moving` set. Unit-tested.
- **Dedupe**: one pre-trip message per driver per warning.
- **Webhook**: `POST /api/photon/webhook` verifies the signature before it changes a case.

## Fallbacks

- Spectrum text only, through `spectrum-ts`: add a ~50-line Node sidecar (`outreach/photon-sidecar/`) with `POST /send` and `/poll`.
- Voice blocked after a 2-hour timebox: fall back to a text poll and log that in [[Decisions]].

## Code

- `backend/outreach/__init__.py` (exists, empty)
- `backend/outreach/base.py` (planned)
- `backend/outreach/mock.py` (planned)
- `backend/outreach/photon_spectrum.py` (planned)
- `backend/outreach/voice_elevenlabs.py` (planned)
- `backend/outreach/log.py` (planned)
- `backend/outreach/photon-sidecar/` (planned, only if needed)
- `.env.example` (exists): `PHOTON_MODE`, `SPECTRUM_*`, `ELEVENLABS_*`, `DEMO_PHONE_*`

> [!warning] No creds yet
> Nothing here is tested against live Photon. Live tests wait for the Spectrum project and iMessage line.

## Related

- [[Stage 1 Pre-trip]], [[Stage 2 En route]], [[Stage 3 Stopped in water]]
- [[Privacy and Consent]]
