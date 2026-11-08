LexForge-Base-v1 public-match study

Target: **LexForge-Base-v1, bot 224**, not the older LexForge/DP/1107 bots. Analyzed all 34 completed matches available at fetch time, IDs 45144–45404, including all 2,312 auctions, archived winning bids, 110 target word plays, final accounts and opponent lineups. This is behavioral reconstruction: the external bot's source and losing sealed bids are unavailable.

Actual target performance

- Mean score **107.68**, median 103.5, range 68–150.
- Mean place **1.735**; 17/34 first-place finishes (ties count as a first place here).
- Mean tiles won 14.18; spend 191.12; final cash 16.56.
- Pooled points per played tile **5.756**. These are played tiles, including the free initial rack; not just auction wins.
- Word lengths: {2: 10, 3: 11, 4: 7, 5: 10, 6: 15, 7: 44, 8: 10, 9: 3}. Unlike GodOfThudner's earlier sample, Base-v1 plays 8- and 9-letter words; imposing a seven-letter cap would copy the wrong behavior.

Observed matchups (strictly higher score, ties excluded from “above”)

| Opponent | Shared matches | LexForge mean | Opponent mean | LexForge above |
|---|---:|---:|---:|---:|
| Primey (191) | 13 | 106.1 | 81.8 | 12/13 |
| RackMaw (193) | 10 | 96.6 | 89.0 | 6/10 |
| bot1717 (204) | 10 | 118.0 | 65.5 | 10/10 |
| Nigel "Bidderson" Richards (205) | 9 | 119.4 | 68.3 | 8/9 |
| GoatBot (213) | 7 | 108.4 | 58.9 | 7/7 |
| SoapConsumers (166) | 7 | 99.9 | 67.6 | 5/7 |
| gas (178) | 6 | 106.2 | 84.2 | 5/6 |
| N1gel (209) | 6 | 101.0 | 83.3 | 5/6 |
| SevenUp (215) | 6 | 100.0 | 72.2 | 5/6 |
| peanuts (188) | 6 | 127.0 | 67.8 | 6/6 |
| Lbender (201) | 5 | 101.8 | 97.4 | 3/5 |
| Astronaut (212) | 5 | 105.0 | 77.2 | 3/5 |
| TileHoarder (187) | 5 | 101.6 | 83.0 | 3/5 |
| LexiconWarrior (181) | 5 | 112.8 | 76.4 | 5/5 |
| Barracuda (162) | 4 | 110.0 | 56.8 | 4/4 |

Word policy reconstruction

All 110 observed plays satisfy at least one of these conditions: a 7+ letter word scoring 45+; balance below 15 with a 5+ letter word; or one or fewer auctions left after the current auction. The 45-point gate explains why it holds weak seven-letter words and high-scoring six-letter words while well funded. Final small-word dumps overwhelmingly occur with one tile still behind the open auction, giving the client time to send successive word reducers.

Primary word selection maximizes reward minus three points per consumed tile, preferring a shorter word when that utility ties. This matches its tendency to retain a common letter when adding it would contribute only three points. Recovery and final liquidation maximize immediate reward. The implemented policy matches the exact word in **98/110** reconstructed states, the reward in **106/110**, and word length in **107/110**. Raw highest-score choice matched reward in only 101/110. Public prefix deficits force all five starting letters in **33/34** source matches; the remaining match uses feasible samples. Residual identity/selection mismatches remain, so this is not an exact source-code copy.

Bid reconstruction

`lexforgeFeatures.ts` uses letter identity, balance and cash per remaining auction, rack size and duplicates, vowel deficit, face value, immediate/long-word gains and primary cash-in completion features. Every feature is available to the live bot. `fit-lexforge.mts` fits a censored normal model: a target win gives its exact archived bid; a loss gives only the winning rival's bid as an upper bound, and a win at the balance cap is treated as right-censored. This avoids treating paid prices as the target's losing bids or pretending all observed winning bids are an unbiased sample.

Oldest 24 matches train the coefficients; newest 10 matches validate. Selected residual scale: 6 coins. Validation winning-bid mean absolute error: **5.12 coins**. A deterministic state-seeded residual reproduces the fitted bid spread and is stable for repeated identical calls. Its true original randomization/decision algorithm is unknown.

Held-out locked-market replay

Replaced bot 224 in the newest 10 matches using eight feasible starting allocations per match. The prior Market7VF and fitted variants see the same letter sequence and frozen rival thresholds. These are replay scores, not live averages or live win rates. Opponents cannot react to changed purchases, and confidence intervals do not cover all model bias. Three residual settings were compared on the validation histories, so selection on them is not a separate untouched performance test.

| Strategy | Mean score: ties lose / reserve rival 1 | Mean score: ties win / reserve rival 0 |
|---|---:|---:|
| market7vf | 59.50 | 58.00 |
| lexforge | 82.10 | 85.50 |
| lexforgeMean | 71.60 | 77.70 |
| lexforgeHalfNoise | 79.90 | 91.70 |

Full fitted residual, ties-lose/reserve-1: paired score gain 22.60, descriptive 95% match-bootstrap interval [12.7, 32.3].

Full fitted residual, ties-win/reserve-0: paired score gain 27.50, descriptive 95% match-bootstrap interval [16.7, 38.7].


The full residual model is deployed as `STRATEGY=lexforge` / LexForgeObserved because it reconstructs the fitted conditional distribution. The mean-only and half-residual variants remain comparison options. This does not establish a 100-point average for our bot: the recorded target is above 100, but the reconstructed policy remains below it in this replay.

Reproduce with:

```sh
REPLAY_INPUT_OUT=bench/results/viability/lexforge-base-input.json node --import tsx bench/live/fetch-replay.mts 100 224
node --import tsx bench/live/study-lexforge.mts
node --import tsx bench/live/fit-lexforge.mts
REPLAY_IN=bench/results/viability/lexforge-base-input.json REPLAY_STRATEGIES=market7vf,lexforge,lexforgeMean,lexforgeHalfNoise REPLAY_AFTER=45320 REPLAY_OUT=bench/results/viability/lexforge-validation-replay.json npm run replay
```

The pinned input, per-auction/word observations, fit metrics and replay results are under `bench/results/viability/lexforge-*`. Refetching newer matches changes the data and split. The original archived evidence remains the reproducible reference for this run.


Newer-game check and deployment

After freezing the source reconstruction, fetched ten games newer than source match 45404 (45413–45489). These games were not used to fit the rules or linear coefficients. Full-residual reconstruction scored **80.1 / 70.9**, versus Market7VF **59.9 / 58.5**, under the two tie/reserve assumptions. Paired gains were +20.2 (descriptive 95% match-bootstrap interval [7.9, 34.6]) and +12.4 ([1.8, 25.9]). The policy has not demonstrated a 100-point average.

A nonlinear censored tree model slightly improved bid-fit likelihood but did not improve replay consistently (69.7 / 78.9). The simpler full-residual linear reconstruction was retained. Other noise settings are experimental comparisons. The newer-game results informed the deployment choice, so future live games are the next independent test. Source bot 224's real 107.7 mean must not be presented as our model's measured mean.

Build and all 35 tests pass, including primary thresholds, five-letter low-cash recovery, penultimate-auction liquidation, preserving useful common letters, fitted dimensions, chronological data splitting, legal bids and repeated-decision stability. `STRATEGY=lexforge` is the deployed default; `STRATEGY=market7vf` remains available for rollback. The server's existing version 2 is retained.
