The simulator matches the engine’s core economics and stock-bot behavior. It does **not** reproduce live policy execution exactly: it replaces asynchronous transactions with a fixed sequence of word plays and bids. Most consequential differences come from that abstraction.

Ranked below by potential effect on match outcomes. Conditional configuration, invalid-input, and replay-only differences are marked explicitly. No files were modified.

1. **Auction deadlines and bot latency are absent.**

   **Engine:** [game.ts:302–303](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:302), [game.ts:631–654](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:631), [index.ts:794–801](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/index.ts:794).  
   **Simulator:** [sim.ts:166–193](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:166).

   Every simulated policy finishes all its word decisions and submits its bid before resolution, regardless of computation or network time. Live bids arriving at or after `closesAt` fail, including replacement bids funded by word rewards. Slow bots can therefore perform substantially better offline.

   Word deadlines differ from bid deadlines: `submitWord` checks whether the match is still `Running`, not whether the current auction’s nominal deadline has passed ([index.ts:819–846](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/index.ts:819)). A word can succeed after that timestamp if the closing transaction has not run.

   **Suggested fix:** Use an event queue with auction deadlines, scheduler execution, policy computation delays, and reducer arrival times. Document zero-latency execution explicitly if that remains an intentional approximation.

2. **All policy word plays finish before any policy bids, creating artificial information and action ordering.**

   **Engine:** [game.ts:613–654](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:613), [index.ts:810](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/index.ts:810), [index.ts:846](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/index.ts:846).  
   **Simulator:** [sim.ts:172–193](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:172).

   Offline, seat 1 completes all its words, then seat 2, and so on; only afterward does anyone bid. Later seats’ word decisions see earlier seats’ updated balances and scores. Every bid sees everyone’s completed word phase.

   Live, auction close, stock-bot word play, next-auction creation, and stock-bot bidding happen in one server transaction. Real bots then submit separate transactions in arrival order. There is no global “everyone finishes words before anyone bids” barrier. Indeed, the live starter sends word reducers asynchronously and immediately attempts its initial bid ([bot-starter/src/index.ts:195–200](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/src/index.ts:195), [284–287](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/src/index.ts:284)).

   **Suggested fix:** Generate reactions from committed snapshots and interleave reducer submissions. At minimum, expose the fixed seat-order assumption and evaluate sensitivity to other reaction orders.

3. **Policies receive only one bidding opportunity per auction; live bids can be replaced or withdrawn.**

   **Engine:** [index.ts:780–810](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/index.ts:780), [game.ts:827–846](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:827).  
   **Simulator:** [sim.ts:182–193](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:182).

   The server replaces a bot’s previous bid, including with zero, until the deadline. The simulator calls `policy.bid` exactly once. Live policies can revise bids after their own word rewards, rack changes, or other observations. Stateful policies also receive a different number of calls.

   The shipped client explicitly rebids on rack changes and its own participant updates ([bot-starter/src/index.ts:289–297](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/src/index.ts:289)).

   **Suggested fix:** Store pending bids separately and allow repeated bid events before close; resolve only the latest accepted bid.

4. **The simulator imposes a hard 30-word limit per policy per auction.**

   **Engine:** [index.ts:816–846](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/index.ts:816).  
   **Simulator:** [sim.ts:79](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:79), [sim.ts:175–179](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:175).

   The engine has no word-count limit while the match is running. Offline, a policy with enough accumulated tiles stops after 30 words, potentially leaving playable words unscored at the final auction.

   The live starter also uses batches of 30, but after settlement it calls `tryPlayWords` again, so 30 is not a hard auction-wide limit ([bot-starter/src/index.ts:163–191](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/src/index.ts:163)).

   **Suggested fix:** Continue until the policy declines, subject to modeled time. A safety limit should report an incomplete simulation rather than silently change gameplay.

5. **Match configuration is supplied independently and is not validated against engine rules. — Conditional**

   **Engine:** [game.ts:48–75](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:48), [game.ts:249–271](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:249), [index.ts:748–762](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/index.ts:748).  
   **Simulator:** [sim.ts:32–37](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:32), [sim.ts:126–140](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:126).

   The engine always starts players at 100 balance; the simulator accepts any `startingBalance`. Starting rack size is configurable on the server, but the benchmark callers hardcode 5 ([run.ts:135](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/run.ts:135), [tune.ts:83](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/tune.ts:83)). Consequently, benchmarks diverge if server rack configuration changes.

   Simulator options also permit negative/fractional rack sizes or racks exhausting the bag. Engine dealing checks for an exhausted draw; simulator dealing does not. With no auction tile remaining, the engine returns `"Bag empty"`; the simulator can return ordinary results without running an auction.

   **Suggested fix:** Import a validated match configuration, enforce starting balance 100 for fidelity runs, and reject impossible configurations before dealing. Keep experimental overrides explicitly separate.

6. **Lobby construction is omitted. — Conditional on simulating a lobby rather than an already selected match**

   **Engine:** [lobby.ts:29–30](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/lobby.ts:29), [lobby.ts:56–93](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/lobby.ts:56).  
   **Simulator:** [sim.ts:117–126](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:117).

   `runMatch` accepts the exact roster and auction type. It does not reproduce lobby timeout padding, selection of distinct eligible simulated bots, filtering of deleted/tournament-held bots, or cancellation below two participants. New ordinary lobbies use Vickrey auctions; the simulator permits either type.

   This can materially alter opponent composition, but is a scope limitation rather than a resolution bug when callers intentionally supply a fixed roster.

   **Suggested fix:** Add a separate lobby-resolution adapter when calibrating against ordinary lobby matches; retain explicit rosters for controlled experiments.

7. **Random tie-breaking consumes randomness differently. — Replay difference; tie probabilities still match**

   **Engine:** [game.ts:555–560](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:555).  
   **Simulator:** [sim.ts:194–196](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:194).

   The engine filters out zero bids **before** shuffling. The simulator shuffles every seat’s bid **before** filtering. If some seats abstain or have zero balance, the simulator consumes extra random draws. Even an auction with no positive bids consumes shuffle randomness offline.

   Given an otherwise shared random stream, this can change the current tie winner and all subsequent jitter and tile draws. It does **not** make positive bidders’ ties nonuniform.

   **Suggested fix:** Filter positive bids first, then shuffle and stable-sort. This will change the benchmark’s deliberately fixed random-consumption behavior described in [run.ts:7–9](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/run.ts:7).

8. **The simulator seed is not an engine replay seed, and pre-shuffle bid order differs. — Replay limitation**

   **Engine:** [game.ts:118–121](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:118), [game.ts:752](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:752), [game.ts:801–823](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:801).  
   **Simulator:** [sim.ts:54–72](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:54), [sim.ts:182–194](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:182).

   Offline randomness comes from caller-supplied `Rng`, commonly Mulberry32. The engine uses transaction-context `ctx.random`; this code provides no equivalent seed/replay mapping.

   Offline shuffle input is seat order. Engine input comes from pending-bid rows: stock bids are inserted during auction creation, real bids arrive later, and replacements delete/reinsert rows. Thus identical shuffle indices need not select identical bots even when every bid is positive.

   **Suggested fix:** For exact replay, record engine random choices and pending-bid ordering, or inject a common deterministic random source and event trace into both implementations. No statistical bias follows merely from these differences.

9. **Word normalization and invalid-action handling differ. — Input-dependent**

   **Engine:** [index.ts:835–846](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/index.ts:835), [game.ts:693–710](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:693).  
   **Simulator:** [sim.ts:102–114](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:102), [sim.ts:188–189](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:188).

   The server uppercases ASCII lowercase input before validation. Simulator membership checking is case-sensitive, so a lowercase word accepted by `submitWord` aborts the simulation.

   More generally, an invalid word or bid rejects one server transaction; the match continues and an earlier accepted bid survives a rejected replacement. Offline, an exception aborts the entire match. `applyWord` also consumes letters incrementally before discovering a missing letter, whereas the engine checks all requirements before consuming any.

   The shipped live starter prevalidates uppercase dictionary membership, so lowercase acceptance matters primarily for direct reducer callers or alternative clients.

   **Suggested fix:** Share server normalization and validation, validate the complete word before mutation, and represent rejected actions without terminating the match.

   **Related live-client difference:** The starter floors and clamps policy bid output ([bot-starter/src/index.ts:210–211](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/src/index.ts:210)); the simulator throws on fractional, negative, or over-balance output. Mirror that adapter when benchmarking the shipped client.

10. **Failed affordability checks produce different auction history. — Defensive branch, unreachable in ordinary valid play**

    **Engine:** [game.ts:576–598](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:576).  
    **Simulator:** [sim.ts:206–208](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:206).

    If the selected winner cannot pay, the engine skips payment and tile delivery but still records that bidder as winner with the calculated `paid` amount. The simulator records no winner and zero paid. Subsequent policies therefore see different histories.

    Normal accepted bids cannot reach this branch: bidding does not escrow money, word play only increases balance, and auctions resolve sequentially.

    **Suggested fix:** Preserve the engine’s recorded result even when delivery fails, or assert the invariant explicitly. Do not silently convert it into a no-bid result.

**Things checked that match**

| Behavior | Finding and references |
|---|---|
| Bag contents | Identical 98-tile A–Z distribution, no blanks: [letters.ts:41](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/letters.ts:41), [lexicon.ts:19](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/src/lexicon.ts:19). |
| Draws | Weighted selection without replacement. The simulator’s ordered expanded bag and `splice` are equivalent to the engine’s alphabetical cumulative counts for matching random indices: [game.ts:744](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:744), [sim.ts:118](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:118). |
| Normal starting state | With standard benchmark options: 100 balance, zero score, five tiles per seat, each seat dealt its complete rack before the next seat. Starting tiles come out of the auction bag. |
| Auction progression | Current tile is removed before bots act; `auctionsLeft` excludes it. One auction per remaining tile. Prior auction settles before the next opens. |
| Sealed bids | Competing pending bids are not exposed to policies. Offline bid collection changes no balances or racks. |
| Resolution | Positive bids only; random shuffle followed by stable descending sort. Tie probabilities agree despite the replay differences above. |
| Payments and reserve | First-price pays own bid. Vickrey pays second-highest positive bid; a lone bidder pays `min(1, bid)`. Tied highest bids pay that tied amount. Losers pay nothing. |
| Unsold tiles | Discarded permanently; never returned to the bag or reauctioned. Zero balances or universal abstention do not end a match early. |
| Stock-bot bids | Exact bases: Cheapskate `value−1`; ValueBidder `value`; Aggressive `value+4` for `AEIOU`, otherwise `value+2`. Inclusive integer jitter −2…2, then identical minimum-one/balance/zero clamping: [game.ts:775](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:775), [sim.ts:81](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:81). |
| Stock-bot words | Only the successful simulated winner acts; exactly one word, after receiving the tile. Minimum length three; longest playable word, alphabetical tie-break—not highest reward. No initial-rack-only play before winning: [game.ts:849](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:849), [sim.ts:217](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/sim.ts:217). |
| Dictionary | Standard benchmark callers load the server wordlist. Checked all 172,820 entries: sorted, unique, uppercase A–Z, lengths 2–28; simulator normalization changes none of them. |
| Scoring | All letter values agree. Multipliers: lengths 2–3 ×1, 4 ×1.5, 5 ×2, 6 ×2.5, 7+ ×3, rounded down. Reward increases both score and balance; bids reduce only balance. |
| Word consumption | Valid words consume exact letter multiplicities. Two-letter words are available to policies; only stock simulated bots require three. Repeated words are permitted if letters remain. |
| Policy inputs | For equivalent committed states, rack, balance, score, opponents, history, auction count, and unseen counts agree with [live.ts:39](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/src/live.ts:39). Unseen counts retain opponents’ hidden starting tiles. |
| Final-auction timing | **Correctly reproduced:** a real policy can play its existing rack during the final auction, but cannot play the final auction’s newly won tile. The engine ends inside the closing transaction; the simulator provides no subsequent policy turn. A stock simulated winner can play that tile before match end. |
| End and placement | Ends after resolving the last auction and its stock-bot word play. No terminal rack bonus, penalty, or balance-to-score conversion. Placement uses score only; tied scores share placement. |

One additional **benchmark reporting** difference sits outside `sim.ts`: the engine counts every top-score tie as a full win ([game.ts:499–507](/Users/sidharthkumar/Documents/GitHub/hackUTD/spacetimedb/src/game.ts:499)), while the runner awards `1/k` win credit ([run.ts:117–120](/Users/sidharthkumar/Documents/GitHub/hackUTD/bot-starter/bench/run.ts:117)). Match scores and places agree, but reported “win rates” are not directly comparable.