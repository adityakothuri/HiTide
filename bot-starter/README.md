ScrabbleBot

`npm start` runs **Market7VF**: Market7V pricing, seven-letter targets and value-scaled pacing, plus completion funding and a first-price affordability cap. The live strategy is selected in `src/strategy.ts`. Experiments and live results are recorded in [bench/EXPERIMENTS.md](bench/EXPERIMENTS.md).

Install and run from `bot-starter/`:

```sh
npm ci
npm run build
npm test

# First connection: use the token generated on your team's page.
BOT_NAME=bot BOT_TOKEN='<your-token>' npm start

# Later connections reuse .token-bot.
BOT_NAME=bot npm start

# Select a strategy explicitly.
BOT_NAME=bot STRATEGY=market7vb npm start
BOT_NAME=bot STRATEGY=market7vc npm start
BOT_NAME=bot STRATEGY=market7vf npm start

# Register for a tournament on connection.
BOT_NAME=bot TOURNAMENT_ID='<tournament-id>' npm start
```

For CLI nonce authentication, use `BOT_NONCE='<nonce>'` instead of `BOT_TOKEN` on the first connection. `STDB_HOST` and `STDB_DB` override the default cloud host and `scrabblebot` database. `QUIET=1` suppresses routine bid/word logging. Keep one process per bot credential; finish the current match and stop that process before switching its strategy.

| STRATEGY | Behavior | Status |
|---|---|---|
| `market7v` | Seven-letter targets, market prices, value-scaled pacing | Previous default; live baseline |
| `market7vb` | Market7V plus 4+ letter cash-in below 35 coins | Live cash-flow experiment; unresolved |
| `market7vc` | Market7Vb plus immediate seven-letter/high-yield six-letter cash-in, endgame liquidation and completion funding | New candidate; requires live validation |
| `market7vf` | Market7V word decisions plus completion funding and first-price affordability cap | Default; live validation ongoing |
| `portfolioTuned` | Earlier portfolio valuation and cash-in regimes | Implemented; simulator evidence only |
| `ha2`, `l1`, `final` | Earlier heuristic/planner strategies | Retained for comparisons; `final` is historical P1, not the default |

Market7VF isolates completion funding while preserving Market7V word decisions. Market7VC carries forward the earlier model's useful cash-in and completion-funding ideas. It keeps Market7V's pricing, caps extra completion spending by current cash and market valuation, and leaves leftover-potential word selection off. It uses an opponent-budget cap in first-price auctions. Before the final auction it respects the seven-letter limit even during emergency cash-in; the final window can liquidate longer words. Its name does not imply that it is better than the live baseline.

The 60-game simulator screen gave Market7V a mean place of 1.70, Market7VC 2.48 and Market7VF 1.67. Market7VF’s difference was too small to establish improvement; Market7VF was subsequently selected for live deployment; this screen alone does not establish an improvement. See E13 for the commands and limitations.

Local checks and comparisons:

```sh
npm run build
npm test
BUDGET_TAU=3 npm run bench -- suite --heroes Market7V,Market7Vb,Market7VC --games 60 --seed 91001 --fields blive

# Earlier portfolio study: 800 offline games across two fields and mechanisms.
EVAL_GAMES=200 EVAL_SEED=730001 EVAL_VARIANT=tuned npm run eval

# Read-only live results for Pegasus (bot id 208), optionally after a match id.
npx tsx bench/live/report.mts 208
npx tsx bench/live/report.mts 208 45175
```

For a faster screen using real market histories (about 40 seconds for the cached 20-match study):

```sh
# Read-only fetch of recent completed matches and archived bids.
node --import tsx bench/live/fetch-replay.mts 20 208
npm run replay

# Optional: compare only the two live-test candidates.
REPLAY_STRATEGIES=market7v,market7vf REPLAY_DEALS=8 npm run replay
```

The replay uses identical observed letter sequences and rival bid thresholds for each candidate. Hidden starting racks are sampled from the aggregate dealt tile pool, constrained by public word/win history, with 2,000 feasible tile swaps to reduce allocation-order bias. Two tie/reserve assumptions test sensitivity. Results and caveats are saved to `bench/results/viability/live-replay-results.json`. Opponents are frozen and cannot react to changed purchases, so these are conditional replay scores, not predicted live win rates. The 20-match screen favors Market7VF by about 2.5–5.8 points, but its uncertainty does not establish improvement under both assumptions. Market7VF is now the user-selected default; live superiority remains unproven.

Simulator results are screening evidence. They previously overrated P1 and do not establish a live winner. Compare candidates for at least 15 completed live matches each on similar tables, recording opponent strength, points per tile, cash starvation and late bids. At the inspection checkpoint, four completed Market7Vb matches in the local log averaged 55.5 points; that sample does not settle the cash-flow question.

The earlier portfolio audit is in [bench/VIABILITY.md](bench/VIABILITY.md), with raw summaries under `bench/results/viability/`. The shared simulator is `src/sim.ts`, re-exported by `bench/sim.ts`; compiled files are written under `dist/`. The bot and simulator load `../spacetimedb/wordlist.txt`, so retain that sibling server directory. Refresh SDK bindings with `npm run generate` when the server schema changes.
