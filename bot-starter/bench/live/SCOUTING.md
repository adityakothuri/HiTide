# Opponent scout

From `bot-starter/`, generate a fresh top-10 report:

```sh
node --import tsx bench/live/scout.mts
```

Continuously refresh rankings and completed-match profiles:

```sh
node --import tsx bench/live/scout.mts --watch
```

Defaults: top 10 real bots, latest 40 completed matches each, refresh 60 seconds after each pass. Set `SCOUT_TOP`, `SCOUT_MATCHES`, and `SCOUT_INTERVAL_SECONDS` to override. Uses `STDB_HOST` and `STDB_DB` when supplied. No bot credentials or match participation needed.

Outputs under `bench/results/scouting/`:

- `REPORT.md`: readable summary and per-letter winning bid percentiles.
- `profiles.json`: structured profiles, separate first-price/Vickrey statistics, match IDs and individual winning observations.
- `matches.json`: reusable completed-match cache, scoped to database host/name.

The collector uses the official leaderboard's OpenSkill display formula and provisional threshold, including tied ranks. It only samples matches from each bot's current version. The watcher discovers newly finished matches on every pass and retains cached evidence after restart. Writes use temporary files and rename. Failed requests retry up to three times; watch mode logs errors and tries again next pass. Run only one scout per output directory. An open foreground process or managed background process is required for continued monitoring; sleeping or shutting down the machine stops local collection.

Winning bids are selection-biased observations. Losing bids and initial racks are unknown. The scout never substitutes a Vickrey paid price for a missing winning bid.

## Scoutroom: clone bots and manage the fleet

```sh
node --import tsx bench/live/dashboard.mts   # http://127.0.0.1:4317  (#fleet opens the Fleet tab)
```

**Scout tab.** Pick one or more leaderboard bots, set copies per bot (1-5), and launch. Selecting a bot fits its clone model and shows held-out fidelity next to the old median-per-letter copy.

**Clone engine v2** (`bench/live/clone-engine.mts`, runtime in `src/clonePolicy.ts`):

- Replays each source match from the bot's seat. Private starting racks are sampled three times per match, consistent with the public auction/word history. Rival cash is tracked through the match.
- Word style: grid-searched play timing (length target, reward floor, recovery cash, liquidation) and word choice.
- Bids: censored-normal regression over 48 state features (rack potentials, cash, rounds left, mechanism, rival budgets). Wins give exact bids, losses give upper bounds and cash-capped wins give lower bounds. Sigma is learned, so the clone reproduces its source's bid spread.
- Validated on the latest 30% of matches, then refit on all of them. Typical results: 83-88% of auction outcomes matched, vs 54-75% for the old copy; winning-bid error ±2-3 points; 77-94% same word reward.
- CLI: `node --import tsx bench/live/clone-engine.mts --bot <id> --out model.json`. Models are cached under `bench/results/scouting/models/` by the source's exact match set. Each copy keeps an immutable `model.json`.

**Fleet tab.** Every clone gets its own team, credential (`.token-<name>`, gitignored) and detached `src/index.ts` process, so any number run at once. Per bot: live status, current match (place, score, cash, progress), local record and recent finishes, live leaderboard rating/rank, and fidelity. Actions: Logs, Drain (finish the match, then exit), Stop, Start/restart, Remove. Bulk Start/Drain/Stop apply to the selection, or to everything when nothing is selected. Bot runners not launched here (such as original Pegasus) are listed separately and can be stopped. Bots survive dashboard restarts and are re-adopted by pid. Signals go only to verified runner processes whose environment names that bot.

Runner environment set by the manager: `CLONE_MODEL_PATH` (play the fitted model), `RESULTS_PATH` (finished-match JSONL), `CONTROL_PATH` (`{"drain":true}` drains), `SCOUT_RUNTIME_PATH` (heartbeat). Registry: `bench/results/scouting/copies.json`. Pre-v2 copies show as LEGACY and still start/stop.

Caveat: clones imitate observed public behavior. They are not the source bots' code. All cached matches are 6-player Vickrey, so first-price behavior is extrapolated: bids are capped at the richest rival's cash + 1.

### Fleet upkeep, deletion and stats

- **Cap:** at most `FLEET_CAP` (default 5) bot runners on this machine, counting runners Scoutroom didn't launch. Launches and starts beyond it are refused.
- **Rebrain / Upgrade to v2:** refits a bot's model, from the same or a different source bot or from our own LexForge strategy, on the same bot id, so its rating carries over. No new server version is started. v2 runners hot-reload `model.json` between matches. Other runners drain and relaunch.
- **Auto-update:** every `MODEL_REFRESH_MINUTES` (default 20), each live clone is refit on its source's newest matches. A refit is kept only if held-out outcome agreement drops by no more than 2 points. Previous models are archived as `model-vN.json`.
- **Watchdog:** a bot that exits unexpectedly is restarted, up to 3 times per 10 minutes.
- **Delete:** permanently removes a bot from the server. Its saved identity is the team's only member, and `leave_team` by the last member deletes the team, bot and credentials. Running bots finish their current match first. This cannot be undone.
- **Stats tab:** every bot whose name starts with `TEAM_PREFIX` (default `Pegasus`). Shows Elo (default sort), leaderboard rating and rank, matches, wins, win %, average points, last played and where it runs. Click a column to sort.
- **One Pegasus per lobby** (`src/index.ts`): the server has a single open lobby. A runner won't join while another bot named `TEAM_PREFIX…` is in it, and joins the next lobby instead. Same-machine races are settled by claim files in `bench/results/lobby-locks/`. Set `ONE_PER_LOBBY=0` to disable. It applies to every runner on this code, on any machine, once restarted.
- **Late bids:** auctions close 1 s after opening. Runners use per-match indexes, bid before searching for words, and skip auctions that have already closed. Each heartbeat reports the share of the last 100 bids that arrived late (Fleet → Status, red above 10%). The low-scoring clones were caused by 25 runners on one machine: 55-75% of their bids arrived late. On-time clone matches averaged 72 points.
- **Bid delay** (Fleet → Status, 0-900 ms, default 0): waits before sending each bid, applied live through the control file. The server keeps bids private (`pending_bid`), so a delay gains nothing; a bid after the window closes is rejected.
- **Rename** (Fleet / Stats) offers two options:
  - *Nickname*: Scoutroom-only display name in `bench/results/scouting/aliases.json`, keeps everything.
  - *Rename on leaderboard*: Scoutroom-registered bots only. The server cannot rename a bot (its name is set once in `create_team`), so this registers a new team + bot under the new name first, then deletes the old bot. A running bot finishes its match before the swap and restarts under the new name. **Elo and match history start over.** If registration fails, the old bot is kept.
- **Themes:** Classic, Pixel (deep-sea pixel art inspired by krillion.io: VT323, abyss blues, stepped borders) and Cyber (neon cyberpunk). Pick one in the header; it's saved per browser. `?theme=pixel|cyber|classic` in the URL overrides it. Styles are in `scout-dashboard/themes.css`.
