# Experiment log

Every row here comes from a run that actually happened. Simulator:
`bench/sim.ts` (mirrors `spacetimedb/src/game.ts`), real ENABLE wordlist
(172,820 words). Runner: `bench/run.ts`. Unless noted: Vickrey auctions,
6-player tables, paired seeds (game i gets the same deal, tile order and sim
jitter for every strategy).

Fields (5 opponents around the strategy under test):
`mixed` = 5 of the 6 lobby sims (2 Cheapskate, 2 ValueBidder, 2 Aggressive);
`agg`/`value`/`cheap` = 5 of one sim; `starters` = 5 repo starter bots;
`reports` = 5 copies of the strategy report's bot; `realmix` = 2 Starter +
1 Report + 1 Aggressive + 1 ValueBidder.

Place is 1-based; bots level on score share the higher place (as Swiss
scoring does). Win share splits ties.

## E1 — Baselines (seed 1, 200 games/field)

`npx tsx bench/run.ts suite --heroes Starter,Report --games 200 --seed 1`

| Field | Starter win / place / score | Report win / place / score |
|---|---|---|
| mixed | 0.5% / 2.97 / 25.0 | 23.0% / 2.35 / 55.2 |
| agg | 0.0% / 5.96 / 10.4 | 7.8% / 5.16 / 10.2 |
| value | 100% / 1.00 / 86.6 | 100% / 1.00 / 185.2 |
| cheap | 100% / 1.00 / 140.4 | 100% / 1.00 / 267.3 |
| starters | 19.3% / 3.21 / 31.3 | 98.0% / 1.03 / 96.8 |
| reports | 2.0% / 4.24 / 37.3 | 23.3% / 3.35 / 61.3 |
| realmix | 0.0% / 4.13 / 16.2 | 8.3% / 2.73 / 40.3 |

Interpretation: on the real wordlist the report's claimed ~100% win share
against stock sims does not reproduce (23% vs mixed, 8% vs Aggressive).

## E2 — Report parameter probes (seed 1, 200 games/field)

| Override | mixed | agg | realmix |
|---|---|---|---|
| none | 23.0% / 2.35 | 7.8% / 5.16 | 8.3% / 2.73 |
| maxBid 40 | 23.0% / 2.35 | 7.8% / 5.16 | 8.3% / 2.73 |
| baseMultiplier 3, maxBid 40 | 100% / 1.00 | 96.0% / 1.09 | 49.0% / 1.54 |
| + vowelPremium 4 | 100% / 1.00 | 100% / 1.00 | 45.8% / 1.56 |
| primaryMinLength 6 | 19.3% / 2.40 | 6.3% / 5.08 | 8.3% / 2.72 |
| primaryMinLength 5 | 15.8% / 2.46 | 1.5% / 5.54 | 9.3% / 2.71 |
| bm 3, maxBid 40, primaryMinLength 6 | 100% / 1.00 | 94.0% / 1.17 | 52.0% / 1.53 |

Interpretation (H1 confirmed): bid level dominates. Score only counts word
rewards and leftover balance is worthless, so the report under-bids. The
play threshold (5/6/7) matters far less than the report claimed.

Note on E2: `--params` overrides apply to every seat with that strategy
name, so in `reports`/`realmix` the opposing Report bots were also tuned.
Those two columns measure "tuned vs tuned", not "tuned vs the report".

## E3 — Strategy A (heuristic + endgame) and B (planner), hand-set (seed 1, 200 games/field)

`npx tsx bench/run.ts suite --heroes ReportHi,HeuristicA,PlannerRef --games 200 --seed 1 --fields 'mixed,agg,realmix,ReportHi*5,PlannerRef*5'`

| Field | ReportHi win / place / score | HeuristicA | PlannerRef |
|---|---|---|---|
| mixed | 100% / 1.00 / 254.4 | 100% / 1.00 / 271.4 | 100% / 1.00 / 242.3 |
| agg | 100% / 1.00 / 190.9 | 100% / 1.00 / 209.2 | 100% / 1.00 / 201.3 |
| realmix | 100% / 1.00 / 267.7 | 100% / 1.00 / 284.1 | 100% / 1.00 / 244.3 |
| ReportHi*5 | 17.5% / 3.35 / 56.8 | 33.9% / 2.40 / 74.9 | 95.0% / 1.05 / 127.4 |
| PlannerRef*5 | 8.0% / 4.87 / 37.4 | 12.7% / 3.81 / 56.0 | 17.5% / 3.44 / 64.2 |

Interpretation: every candidate saturates against stock bots, so tuning
uses tough fields. The endgame cash-in (play everything and spend the whole
balance on the last auction) helps in every field. Hoarding for 7-letter
words collapses against strong bidders (ReportHi plays 1.5 words/game there);
the planner keeps playing (~9 words/game).

## E4 — Random search, round 1 (dev seed 1001, 100 games/field)

Objective: mean finishing place averaged over `ReportHi*5`, `PlannerRef*5`,
`HeuristicA*5`, `PlannerRef*2+ReportHi+Aggressive+ValueBidder` (lower is
better; 1.0 = always first). Planner: 56 configs (sample seeds 11–17).
HeuristicA: 16 configs (sample seed 21). Raw rows:
`bench/results/tune-planner-r1.jsonl`, `tune-heuristicA-r1.jsonl`.

| Rank | Strategy | Objective | Per field |
|---|---|---:|---|
| 1 | Planner P1 | 1.090 | 1.06 / 1.16 / 1.07 / 1.07 |
| 2 | Planner P2 | 1.120 | 1.06 / 1.12 / 1.18 / 1.12 |
| 3 | Planner P3 | 1.185 | 1.02 / 1.51 / 1.10 / 1.11 |
| 4 | HeuristicA A1 | 1.205 | 1.10 / 1.24 / 1.22 / 1.26 |
| 5 | HeuristicA A2 | 1.208 | 1.00 / 1.61 / 1.00 / 1.22 |
| ref | PlannerRef (hand-set) | 1.957 | |

Worst configs scored ~5.5 (mostly under-bidding).

## E5 — Validation on a fresh seed (seed 2002, 200 games/field)

Raw rows: `bench/results/validate-v1.jsonl`.

| Config | Round 1 (seed 1001) | Validation (seed 2002) |
|---|---:|---:|
| HeuristicA defaults (ReportHi+End) | — | 3.179 |
| HeuristicA A1 | 1.205 | 1.244 |
| HeuristicA A2 | 1.208 | 1.291 |
| PlannerRef | 1.957 | 2.011 |
| Planner P1 | 1.090 | **1.068** |
| Planner P2 | 1.120 | 1.239 |

Interpretation: P1 holds up on unseen games; P2's round-1 score was partly
luck.

## E6 — HeuristicA round 2: local refinement (seed 1001, 100 games/field)

12 variants of A1/A2 at +-25% (sample seeds 31, 32). Best: 1.105
(1.01/1.28/1.03/1.10) with baseMultiplier 4.116, vowelPremium 5.561,
commonPremium 2.651, balanceCorrection 7.396, duplicatePenalty 3.848,
maxBid 33, primaryMinLength 8, pressureRackSize 9, emergencyMinLength 3.
Raw rows: `bench/results/tune-heuristicA-r2.jsonl`.

## E7 — Live data: what the strong bots on the server do (400 recent matches)

`npx tsx bench/live/profile.mts 400` (read-only public tables). All 400
matches Vickrey, 6 bots per table. Mean winning bid 15.0, mean price paid
10.6. Top bots: LUCENT mean place 1.76, 55% wins, 151 points, 23.4 tiles won,
70% of words 7+ letters; Bron 1.93 / 38% / 137 / 21.4 tiles. Fitted bids
(winning top bid ~ a*face + b): LUCENT 2.78*face + 9.2, Bron 2.29*face + 8.6,
GodOfThudner 2.59*face + 12.0 (resid sd 6-7). Stock sims score 1-23 live.
No real bot wins the final auction (none goes all-in there).

## E8 — Live head-to-head, P1 as bot "Pegasus" (id 208), 7 finished matches

`npx tsx bench/live/report.mts 208`. Mean place **4.71**, 0 wins, mean
score 58.9 (opponents 40-125). From the bot log: P1 won only 3-8 of 68
tiles per match; when it lost, the winner paid a median 3-5 more than P1
bid. Word play converted well (one 7-9 letter word per match, 39-81 points).
Diagnosis: P1 was tuned against fields whose prices are far below the live
market (~10-14 per common tile), so it under-bids live. Live bot paused.

Mimic calibration: copying the fitted bids with naive hoarding play
(`M-*`) reproduces live prices but not live scores (mimics finish with ~7
unplayed tiles and go broke), which made low bidders look good (P1 82% vs
`live` field, 150 games, seed 3003). Giving mimics the planner's play
(`S-*`) brings unplayed tiles to ~1.8 and scores to 66-103.

## E9 — Calibrating opponents to the live market

`bench/live/market.mts` (Codex-written, 400 live matches): median price
paid by letter (vowels ~10, T/N/L/R ~10-11, B/C/M/P 15-17, H/Y 19, K 22,
J 25, X 26, Z 32); opening phase dearest (14.0 paid), ~12 after. Each match
spends ~870 of ~1030 total money (600 start + ~430 scored).

Calibration of simulated tables (seed 7/9, 40 games, 6 bots, mean winning
bid / mean paid; live 15.0 / 10.6):
6 x P1 planners at bid level 1x: 16.7 / 11.9; 1.5x 19.9 / 12.4; 3x 28.8 /
12.0 (price paid is budget-bound, ~12 at any bid level). Budget-aware live
copies (`B-*`, fitted bids + planner play + spend throttle tau): tau 3 ->
15.4 / 11.9 with common letters 10-11 like live (high letters ~25% cheaper
than live); tau 5 -> 13.2 / 10.4; tau 8 -> 11.0 / 8.7. `B-*` at tau 3 is the
tuning target from here on.

Codex audit of `bench/sim.ts` vs the engine (`bench/results/codex/
sim-audit.md`): no rule bugs; known abstractions are zero latency, one bid
per auction, seat-ordered word plays, different random consumption.
Codex also made the planner ~3x faster with exact equivalence on 3,036
random cases (`bench/check-planner-equivalence.ts`, independently re-run).

## E10 — Live A/B on the server (bot "Pegasus", id 208)

`npx tsx bench/live/report.mts 208`. Live tables vary a lot in strength
over time (early: weak bots scoring 0-30; later: GodOfThudner, StickBot,
Lbender, SevenUp scoring 100-150), so compare runs played close together.

| Strategy | Matches (ids) | Mean place | Wins | Mean score |
|---|---|---:|---:|---:|
| P1 | 8 (43021-43064) | 4.75 | 0 | 51.5 |
| HA2 | 5 (43211-43241) | 3.20 | 1 | 77.2 |
| L1 | 5 (43248-43276) | 4.40 | 1 | 68.8 |
| D (Market, unpaced) | 5 (43284-43312) | 4.00 | 1 | 61.2 |
| D paced K=12 | 4 (43319-43340) | 4.00 | 0 | 65.5 |
| D paced + word-choice search | 2 (45056-45063) | 3.50 | 0 | 68.0 |
| HA2 rerun on current tables | 6 (45069-45101) | ~5.5 | 0 | ~42 |

Diagnoses from the bot logs: P1 won 3-8 of 68 tiles (outbid by 3-5);
unpaced D overspent early and was stuck bidding 4-6 for ~55 auctions;
pacing fixed that (bids 8-19 all match, 14-16 tiles won). HA2's early
record came from weaker tables: rerun on current tables it averaged ~5.5.

## E11 — What the strongest live bot does differently

14 matches shared with GodOfThudner (live, 43284+): GodOfThudner 110
points/match from 20.6 tiles played (5.36 per tile); Pegasus 61 from 14.4
(4.25). GodOfThudner wins more 2-3pt (3.3 vs 1.6/match), 4-5pt (2.3 vs 0.8)
and 8-10pt (0.7 vs 0.2) letters and fewer 1-pt consonants (3.0 vs 4.3); it
played **no word longer than 7 letters** (0 of 55; 22 of exactly 7), while
Pegasus played 8 words of 8-11 letters.

Changes and sim checks (B-* field, 60 paired games, seed 8008):
| Variant | Mean place | Win % |
|---|---:|---:|
| paced D (MarketP12) | 2.05 | 52% |
| + 7-letter cap (Market7) | **1.68** | 65% |
| + 7-letter cap + group anchors (Market7G) | 1.82 | 59% |
| group anchors only (MarketG) | 2.05 | 53% |

Rejected: word choice by reward + leftover potential (`playSearch`, seed
6006): 2.45 vs 1.80 for paced D; it cashes in short words too early (also
seen live: GROWN, GEMOT, GAL).

Extreme-value sweep (seed 7007, 60 games x 2 B-* fields, 49 of 71 configs
at time of writing; `bench/results/sweep-*.jsonl`): early cash-in is worst
(planner holdMargin 0.8: 4.61), budget starvation bad (D maxBidShare 0.2:
3.83), extreme anchors bad (0.3x: 4.95, 3x: 3.39), spend rate has a sweet
spot (spendMin 1.0: 1.73 vs 0.6: 3.68, 2.5: 3.28). The sim prefers anchors
below live prices (0.6x: 1.70), which conflicts with live evidence of being
outbid, so live results decide.

## E12 — Live-bot timing fix and current state (checkpoint)

The live bot rebuilt a full snapshot for every auction of every match on
the server; on a busy server its bids arrived after close (whole matches
lost). `src/index.ts` now ignores other matches' events: late bids went from
a full match to 0 of 70. Market7V (7-letter cap + value-scaled pacing) is
the shipped default; live record so far is small (mean place ~4.5) and the
cash-in-when-broke variant (Market7Vb) was mid-test. The sim prefers fewer
early cash-ins; live shows a cash-flow trap — unresolved.

## E13 — Earlier portfolio ideas as isolated Market7V candidates

Added two opt-in strategies without changing the Market7V default or the
match-filtering/word-event fixes in `src/index.ts`:

- `STRATEGY=market7vc` (Market7VC): Market7Vb pricing/pacing, immediate
  seven-letter cash-in, six-letter cash-in at 24+ points, staged endgame
  liquidation, and more bidding room for a tile needed by an immediate
  cash-in. Completion spending stays bounded by current cash, 60% balance,
  the unpaced market bid, and 95% of the cash-in reward (shaded in first-price).
- `STRATEGY=market7vf` (Market7VF): isolates the same completion funding,
  retaining Market7V word decisions and its below-12 cash recovery. Both
  candidates cap first-price bids at the richest rival's balance plus one.

Leftover-potential word selection remains off. Fixed `market.ts` emergency
cash-in, which previously bypassed `plan.maxWordLength`; emergency plays
now respect the seven-letter cap. The final window can still liquidate
longer words. Existing `portfolioTuned`, HA2, L1 and historical P1 remain
selectable; none was promoted based on simulator results.

Screening only: 60 paired games per strategy, seed 91001, budget-aware
live-mimic field with `BUDGET_TAU=3`. Not a live A/B test. Commands:

```sh
BUDGET_TAU=3 npm run bench -- suite --heroes Market7V,Market7Vb,Market7VC --games 60 --seed 91001 --fields blive
BUDGET_TAU=3 npm run bench -- suite --heroes Market7V,Market7VF --games 60 --seed 91001 --fields blive
```

| Strategy | Mean place | Win share | Mean score |
|---|---:|---:|---:|
| Market7V | 1.70 | 59.2% | 93.4 |
| Market7Vb | 1.92 | 53.1% | 84.2 |
| Market7VC | 2.48 | 39.2% | 76.0 |
| Market7VF | 1.67 | 60.6% | 94.7 |

Market7VF's paired place difference is -0.03 ± 0.29 (reported 95% interval
half-width); there is no demonstrated improvement. The combined cash-in
regimes underperform in this screen. Raw outputs:
`bench/results/viability/conversion-smoke.txt` and `funding-smoke.txt`.
Market7VF decision time averaged 0.302 ms, maximum 20.4 ms; these policy
measurements do not include live event processing or network delay.

Read-only local-log checkpoint: Market7Vb completed matches 45176, 45183,
45191 and 45198 scored 68, 40, 56 and 58 (55.5 mean). The Market7V rerun
completed 45155, 45162 and 45169 scored 63, 40 and 66 (56.3 mean). These are
small sequential samples on changing tables, not evidence for or against
the below-35 cash-flow rule. Existing live processes were left untouched;
no 15-match candidate comparison was started by this work.

Validation: `npm run build`; `npm test` (21 passing tests), including
required-letter completion funding, first-price affordability, seven-letter
emergency cap, endgame liquidation and unchanged Market7VF word decisions.
README now documents authentication, strategy selection, tournament entry,
local benchmarks and read-only live reporting. Next useful live comparison:
Market7V versus Market7VF, with Market7Vb's cash-flow result kept separate.
