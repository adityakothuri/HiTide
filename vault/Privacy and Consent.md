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

## Security scan results (2026-11-07)

### ECC `security-reviewer` agent: app code
No CRITICAL. No secrets or real phone numbers in git history. `pip-audit` found no known vulnerabilities. `npm audit` found 14 moderate, all transitive through `spectrum-ts` → `@opentelemetry/core`, with no fix available.

| Finding | Severity | Status |
|---|---|---|
| Exact age and vehicle in `urgency_reasons`, sent to every client | HIGH | **Fixed** (TDD): coarse bands like "older driver (65+)" |
| Emergency contact name in the case timeline | HIGH | **Fixed**: "emergency contact" |
| WS readable and demo resettable from any web page | HIGH | **Fixed**: same-origin guard on `/ws` and POSTs (`backend/app/security.py`) |
| Driver locations shared before any warning | MEDIUM | **Fixed**: no locations in the snapshot or `drivers.update` until an alert is active |
| CORS trusted all LAN origins | MEDIUM | **Fixed**: localhost by default, `FRONTEND_ORIGIN_REGEX` to pin another |
| `/api/cases/{id}/reply` has no auth (LAN curl) | MEDIUM | Accepted for the demo. Browser cross-site is blocked by the origin guard. A real app would use driver auth. |
| `/api/drivers/{id}` returns the driver's own vehicle | MEDIUM | Accepted: it's the driver's own app view. Needs auth in a real app. |
| No rate limiting | MEDIUM | Accepted for the demo. Outbound sends only go to allowlisted numbers. |
| Sidecar key compared with `!==` | LOW | **Fixed**: `crypto.timingSafeEqual` |
| Feed client followed redirects | LOW | **Fixed**: redirects off |

**Privacy rules after fixes:** all six rules pass. Live location is shown only during a warning. Age and vehicle only order outreach and are never exposed raw. Responders get `ResponderView` only. Numbers live only in `.env`. No numbers appear in logs or WS. Texts go only to allowlisted numbers. Enforced by `backend/tests/test_demo_flow.py`.

### ECC `security-scan` skill (AgentShield 1.6.0): `.claude/` config
Grade **D (54/100)**, 0 critical, 1 high, about 100 medium.
- The **high** is a false positive: "skip validation" in a Ruby review checklist (`agents/ruby-reviewer.md:55`).
- The mediums are almost all ECC's own templates (`mcp-configs/` examples, not active servers) and ECC's long inline hook bootstrap.
- Secrets: 100/100.
- Action taken: added a `permissions.deny` list (`.env` reads and writes, `sudo`, `ssh`, `rm -rf /`, force push, `chmod 777`, writes to `/dev`).
- The score dropped slightly (57 → 54) because a permissions block switches on extra deny-rule checks. We added those rules too.
