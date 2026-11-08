Implemented sparse letter scans, reused odds powers, and safe early exits while preserving evaluation order.

All **3,036 equivalence cases passed**, including exact floating-point potentials and identical bids/plays.

Timings in milliseconds, **before → after**:

| Operation | Mean | p99 | Max |
|---|---:|---:|---:|
| Potentials | 3.556 → 1.554 | 18.461 → 5.627 | 30.271 → 10.831 |
| Bid | 2.887 → 1.515 | 12.799 → 5.644 | 17.867 → 9.806 |
| Play | 7.343 → 2.056 | 30.983 → 7.550 | 49.474 → 11.896 |
| Bid + play | 10.231 → 3.572 | 39.875 → 12.316 | 57.038 → **19.361** |

Type checking and all six tests passed. Only the three permitted files changed.

The sandbox blocked `npx tsx` from opening its IPC socket; the benchmark passed using `node --import tsx bench/check-planner-equivalence.ts`.