---
tags: [hitide, evidence, integration, mongodb]
updated: 2026-11-07
---

# Evidence-to-inspection milestone

Current detailed handoff: [State of the Union](../../docs/STATE_OF_THE_UNION.md).

## Delivered

- Source-attributed observations, measurement vs ingestion time, revision history,
  semantic deduplication, source-attempt diagnostics.
- Default MongoDB persistence, replica-set transactions, `2dsphere` nearby and
  intersection queries; explicit SQLite test/development alternative.
- Directed neighborhood access analysis, uncertain last-exit priority, inspection
  assignment/result feedback, inconclusive handling, and restart persistence.
- Operations console at `/console`, local reports, source status, evidence details,
  accessible offline road geometry, and explicit simulation labels.
- NWS/USGS normalizers and legacy gauge fallback-provenance correction.
- VS Code startup tasks, local Mongo helper and optional authenticated Claude
  read-only review runner using checked-in ECC agent definitions.

## Integration and validation

Merged teammate updates through `bc15367` before publishing. Preserved Photon 2.0
inbound startup, voice-task cancellation, same-origin guards, bridge corrections,
and YOLO pipeline work. The evidence router also uses the origin guard.

- Backend: **373 passed** with actual local MongoDB enabled.
- Evidence package coverage: **94%** statements.
- Frontend: **78 tests passed**, production build passed.
- Browser: **2 Playwright evidence tests passed** with mocked API and installed Chrome.
- Real database/app tests cover rollback, geographic indexes, and an inspection
  surviving a full FastAPI restart. These are separate from the mocked browser tests.

## Problems found and resolved

- Missing local Python/uv dependencies; installed Python 3.12 and dependency groups.
- ECC audit dependency missing; supplied `@iarna/toml` locally under `.claude/`.
- Database missing transaction/health helpers and retrieval-metadata dedup behavior;
  targeted tests captured RED then GREEN.
- Gauge history fallback could inherit the wrong endpoint's source/fetch time.
- Test selector matched both a summary and an exact community label; tightened locator.
- Mongo archive extraction failed in PowerShell; use native tar after checksum verification.
- Mongo startup exhausted local disk headroom; removed the verified installer archive
  created by this task, retained user data, and bounded the local oplog/cache settings.
- Teammate tests assumed Unix `0600` mode bits; content checks remain cross-platform,
  permission-bit checks now apply only on non-Windows. Windows ACLs remain unverified.

## Honest boundaries

No physical drone, Atlas provisioning, Gemini integration, State Farm telemetry,
validated flood-depth model, live TxDOT closure adapter, or statewide coverage was
added. A full live browser/backend/Mongo demonstration remains a manual final check.
The existing driver simulation and the new evidence assessments are not yet joined.
Claude CLI was not signed in; native agents applied ECC instructions, while only
the deterministic harness audit was actually run through the bundled scripts.
