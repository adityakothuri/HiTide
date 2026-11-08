---
tags: [floodwatch, privacy, security]
status: in-progress
updated: 2026-11-07
---

# Privacy and Consent

Flood Watch handles live location and personal data. These rules are shown in the app and enforced in code.

## Rules (from the project brief, section 12)

1. **Opt-in.** Flood Watch is opt-in in the State Farm app. Live location is shared **only during an active flash flood warning**.
2. **Emergency contacts are added by the customer.** We never infer them.
3. **Age and vehicle data only affect outreach order, never pricing.** See [[Risk Scoring]].
4. **Responders see location, number of people, and water depth only.** This is the `responder_view` object in the [[Architecture|API contract]].
5. **Run the ECC security scan before submission and record the results here.** See [[Tooling]].

## Demo-specific rules

- Real phone numbers are used only for teammates who agreed. They live in `.env` (`DEMO_PHONE_A/B/C`, gitignored) and are never committed. `data/drivers.json` stores only `env:DEMO_PHONE_X` references.
- Outbound messages go only to allowlisted numbers. Every other driver is mock-only.
- Every outbound message is logged to `data/outreach_log.jsonl` (gitignored).
- The UI labels simulated parts as simulated: the alert, thermal frames, mock outreach, and manual water-level labels.

## Where it is enforced in code

| Rule | Code |
|---|---|
| Responder fields only | `backend/api/schemas.py` (`ResponderView`) |
| Allowlist + log | `backend/outreach/allowlist.py`, `backend/outreach/log.py` (no numbers in the log) |
| No texts to a moving driver | `backend/outreach/service.py` guard, `backend/tests/test_outreach_guard.py` |
| Inbound replies only from allowlisted numbers, key-guarded | `backend/api/routes.py` `/api/photon/inbound`, `photon-sidecar/index.mjs` |
| "not safe" never resolves a case | `backend/outreach/replies.py`, `backend/tests/test_reply_parse.py` |
| Secrets via env | `.env.example`, `backend/app/main.py` (`load_dotenv`) |

## Security scan results

> [!todo] Run the `security-scan` skill and the `security-reviewer` agent before submission, then paste the results here.
