# Outreach

Sends texts, polls, voice calls and in-app TTS for flood alerts.
Entry point: `make_outreach(emit, is_moving)` -> `await svc.send(OutboundMessage(...))`.

## Modes
- mock (default): nothing leaves the machine; events have mode "mock", status "sent".
- photon: `PHOTON_MODE=photon` AND the number resolves via `env:DEMO_PHONE_X`. Real numbers never resolve.
- Guard: text/poll/voice to a moving driver is "blocked" (logged + emitted). tts_in_app, parent, emergency_contact always pass.
- Log: `data/outreach_log.jsonl`, one JSON line per attempt, never contains phone numbers.

## Env vars
- PHOTON_MODE, DEMO_PHONE_A / B / C (consented teammate numbers, E.164)
- SPECTRUM_PROJECT_ID, SPECTRUM_PROJECT_SECRET, SPECTRUM_LINE (read by the Node sidecar)
- SPECTRUM_SIDECAR_URL (default http://localhost:8787)
- ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID, ELEVENLABS_PHONE_NUMBER_ID

## Spectrum sidecar (not built yet)
Spectrum REST has no send endpoint; only spectrum-ts can send. The adapter expects
`POST /send {to, body}` and `POST /poll {to, question, options}` on the sidecar.

## Live test once creds arrive
1. Start the sidecar with SPECTRUM_* set; export PHOTON_MODE=photon and DEMO_PHONE_A=+1...
2. Voice: set ELEVENLABS_*; point the ElevenLabs SIP trunk at sip.spectrum.photon.codes:5061 (TLS) in its dashboard.
3. From `uv run python`, send a text to env:DEMO_PHONE_A via make_outreach and check your phone.
4. Without ELEVENLABS_* a voice send falls back to an "Are you okay?" poll.
