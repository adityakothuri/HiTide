The prompt's tournament-winning claim is not supported by this implementation and benchmark. Its strongest information advantage is unavailable under this repository's actual rules. A corrected implementation is fast on ordinary racks and becomes competitive after increasing bids, but it does not establish first place in both average score and win share.

Server audit

- `spacetimedb/src/game.ts:startMatchWith` deals **five private starting tiles per bot** by default. Six bots therefore leave 68 auction tiles, not 98. `startingRackSize`, lobby size and auction duration are configurable.
- Public wins minus public word consumption cannot determine an opponent's private starting rack. `stateTracker.ts` exposes guaranteed current letters and an unresolved tile count instead. Balances and scores are directly public in `match_participant`.
- `drawLetter` decrements the bag when a tile is drawn. `closeAuction` never returns an unbid tile. Bag composition is therefore not “98 minus won tiles”; discarded tiles, the open tile and hidden starting racks all matter. `match_state.bag_total` gives the exact remaining total, but not its composition.
- `auction_result` contains `paid`, but **no `top_bid`**. `spacetimedb/src/index.ts:visibleAuctionTopBids` explicitly returns no rows for identities holding bot credentials. Winning bids are archived publicly after the match. This implementation uses paid-price history only.
- `playWord` calculates `(baseScore * numerator) / denominator` using bigint integer division. Positive rewards are floored and added to **both** score and balance, as the prompt states.
- The final auction closes and ends the match in one server transaction. An external client cannot use its winning tile afterward. Existing tiles must be cashed in during the final auction window. The portfolio candidate skips the unusable final tile.
- Reducers are `submitBid({ auctionId: bigint, amount: bigint })` and `submitWord({ matchId: bigint, word: string })`. The server bundles `spacetimedb/wordlist.txt`; the bot loads that same 172,820-word file from disk.

Implementation

`src/dict.ts` reuses the existing typed-array lexicon rather than building a second index. Playable results are reward-sorted, masks prune impossible words, and cached analyses provide leave values and one-letter completions. Completion value takes the best word per missing letter instead of summing mutually exclusive anagrams. The storage index remains length-sorted to preserve existing planner interfaces.

`src/stateTracker.ts` rebuilds idempotently from the per-match cache. Opponent racks are conservative lower bounds. Bag letter estimates allocate the unresolved public tile pool proportionally to the exact bag total; this is an exchangeability heuristic, **not an exact posterior**. Opponent blocking only acts on guaranteed known tiles. It cannot implement the prompt's exact-rack denial exploit.

`src/strategies/portfolio.ts` implements marginal portfolio bids, cash-in liquidity relaxation, first-price shading, opponent-affordability caps, rack bloat limits and the five word-play regimes. Eligible words are filtered before maximizing reward plus leave. Refunds do not permit borrowing beyond current balance. The requested broad strategy leaves numerical weights unspecified; the original configuration is one explicit operationalization, not a test of every possible tuning of the idea.

`src/strategy.ts` exports the candidate and parameters and adds `portfolio` and `portfolioTuned` selectors. The default live strategy is unchanged. `src/index.ts` also responds to auction results and balance changes, includes balance in decision debouncing, and waits for each word reducer before selecting another word. Live reducer timing/concurrency has been reviewed and typechecked, but was not integration-tested against a running server during this evaluation.

Experiment design

The evaluator reuses the existing simulator, now shared as `src/sim.ts` and re-exported by `bench/sim.ts`, including six players, private five-tile deals, random tie-breaking, first-/second-price payments, positive bid reserve, discarded unbid tiles, dual rewards, and no external-client reaction after the last close. Opponent observations are built from public auction/play history; private racks are not passed to policies. This is a local behavioral simulation, not an execution of the actual SpacetimeDB reducers or a network latency test.

The `requested` field contains StarterBot, GreedyShortBot (immediate play, bids twice face value), BlindHoarderBot (7+ letter cash-in, bids three times face plus four), HeuristicVickreyBot (the existing marginal planner reference), and the repository's existing Final strategy as the fifth opponent. The `strong` field contains Final, L1, HA2, MarketPS and the planner reference. These baselines are explicitly defined in `src/eval.ts`; the heuristic reference reuses an existing planner rather than being an independent new implementation.

Seats rotate across games. Win share splits first-place ties; mean place follows the server's shared placement convention. This differs from the server's raw win counter, which counts every tied first as a win. The reported 95% score intervals use normal sampling approximations; individual win-share intervals use a Wilson-style approximation with fractional tie credit. Pairwise score differences use a conservative normal critical value of 3.25; pairwise win-share differences use Hoeffding bounds with a family adjustment across 40 comparisons. Score inference is approximate. No significance calculation proves superiority over unknown tournament opponents.

The starting configuration ran 200 games (50 per cell, seed 710001). It won none. Its raw normal win intervals are exploratory and should not be used for inference. One development probe raised bid floors and marginal weights, reduced the reserve and relaxed the spending cap: 100 games (25 per cell, seed 720001). No parameter search was performed on the final validation seeds. Validation used 800 fresh games (200 per cell, seed 730001), with disjoint mechanism/field seed offsets.

Final held-out results

| Auction | Field | Candidate mean score | Win share | Mean place | Score rank | Win rank | Highest mean score | Highest win share |
|---|---|---:|---:|---:|---:|---:|---|---|
| Vickrey | requested | 84.02 | 13.50% | 2.44 | 3/6 | 3/6 | Final (91.28) | BlindHoarderBot (44.75%) |
| Vickrey | strong | 68.31 | 18.50% | 3.15 | 2/6 | 4/6 | MarketPS (68.94) | L1 (20.75%) |
| FirstPrice | requested | 83.49 | 51.25% | 1.65 | 1/6 | 1/6 | Portfolio (83.49) | Portfolio (51.25%) |
| FirstPrice | strong | 69.17 | 22.25% | 2.92 | 2/6 | 2/6 | HA2 (85.33) | HA2 (55.50%) |

Vickrey / requested: candidate score 95% interval [81.62, 86.42], win-share interval [9.45%, 18.93%]. All-opponent superiority supported: **false**.

Vickrey / strong: candidate score 95% interval [66.18, 70.45], win-share interval [13.73%, 24.46%]. All-opponent superiority supported: **false**.

FirstPrice / requested: candidate score 95% interval [81.59, 85.39], win-share interval [44.36%, 58.09%]. All-opponent superiority supported: **false**.

FirstPrice / strong: candidate score 95% interval [67.03, 71.30], win-share interval [17.04%, 28.51%]. All-opponent superiority supported: **false**.

Performance and verification

Dictionary startup: 89.6 ms. Full 800-game run: 242.1 seconds (60.5 seconds per 200 games on average), so the requested ‘few seconds’ throughput target was not met.

Candidate bid: 54400 calls; p50 0.007 ms, p95 0.178 ms, p99 0.288 ms, maximum 2.096 ms. These timings cover the policy functions, not subscription decoding, state reconstruction or reducer round trips. They are measurements rather than a hard latency guarantee.

Candidate play: 57739 calls; p50 0.003 ms, p95 0.005 ms, p99 0.051 ms, maximum 5.640 ms. These timings cover the policy functions, not subscription decoding, state reconstruction or reducer round trips. They are measurements rather than a hard latency guarantee.

The final source passes `npm run build` and the 15 regression tests in `npm test`, covering legal bids/words, floor arithmetic, duplicate letter counts, anagram EV, exhausted completions, hidden starting racks, discarded tiles, final-close timing, liquidity recovery and edge-case decisions. Tests do not establish a worst-case 10 ms end-to-end bound.

Interpretation

The fast dictionary, endgame liquidation and liquidity-aware cash-in are useful components. The exact public-state exploit is invalid for default matches. Marginal immediate value alone leaves many useful early purchases undervalued: a tile can be essential several acquisitions before it creates a word or a one-letter completion. Higher bid floors helped substantially, but those floors are heuristic acquisition spending, not a derived equilibrium valuation. A second-price auction with future budgets and denial externalities also does not inherit the simple isolated-auction truth-telling guarantee.

Further work should compare market-calibrated multi-step acquisition value and alternative cash-in thresholds on separate development seeds, then validate against diverse strong opponents and actual server timing. The current evidence supports retaining this as an opt-in research candidate, not replacing the existing strategy or claiming a statistically established tournament winner.

Reproduce with `EVAL_GAMES=200 EVAL_SEED=730001 EVAL_VARIANT=tuned EVAL_OUT=bench/results/viability/validation.json npm run eval`. Full parameters, intervals and per-opponent comparisons are recorded in `bench/results/viability/{original,development,validation}.json`.
