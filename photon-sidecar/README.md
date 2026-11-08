# Photon sidecar

Spectrum's REST API can't send messages, so this ~80-line Node bridge sends through `spectrum-ts`.

```bash
cd photon-sidecar && npm install && npm start      # reads ../.env
```

Needs `SPECTRUM_PROJECT_ID`, `SPECTRUM_PROJECT_SECRET` and `SIDECAR_KEY` (any random string, shared with the backend) in `.env`. Then set `PHOTON_MODE=photon` for the backend.

- `POST 127.0.0.1:8787/send {to, body}`: iMessage text
- `POST 127.0.0.1:8787/poll {to, question, options}`: native poll ("I'm safe" / "I need help")
- Inbound texts and poll votes go to `POST {BACKEND_URL}/api/photon/inbound {from, text}`. The backend matches `from` against `DEMO_PHONE_*` and resolves or escalates the case.
