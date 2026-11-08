// Read-only check of the bot's live subscription: connect anonymously (no
// token, so it can't bid or play), subscribe as the bot does, and report
// row counts, timing and memory. Then watch running matches for a while
// and build the strategy's view from live data each auction.
//
//   npx tsx bench/live/connect-test.ts [seconds=20]

import { Lexicon } from "../../src/lexicon.js";
import { buildView } from "../../src/live.js";
import { DbConnection } from "../../src/module_bindings/index.js";
import { STRATEGY } from "../../src/strategy.js";
import { subscribeForBot } from "../../src/subscribe.js";

const SECONDS = Number(process.argv[2] ?? 20);
const lexicon = Lexicon.fromFile(new URL("../../../spacetimedb/wordlist.txt", import.meta.url));
const t0 = performance.now();
let auctions = 0;
let maxDecisionMs = 0;

DbConnection.builder()
  .withUri(process.env.STDB_HOST ?? "https://maincloud.spacetimedb.com")
  .withDatabaseName(process.env.STDB_DB ?? "scrabblebot")
  .onConnect((conn) => {
    console.log(`connected in ${(performance.now() - t0).toFixed(0)} ms (anonymous, read-only)`);
    subscribeForBot(
      conn,
      () => {
        const count = (it: Iterable<unknown>) => [...it].length;
        console.log(`subscribed in ${(performance.now() - t0).toFixed(0)} ms`);
        console.log(`rows: match_state ${count(conn.db.matchState.iter())}, match_participant ${count(conn.db.matchParticipant.iter())}, auction ${count(conn.db.auction.iter())}, auction_result ${count(conn.db.auctionResult.iter())}, word_play ${count(conn.db.wordPlay.iter())}, bot ${count(conn.db.bot.iter())}`);
        console.log(`heap ${(process.memoryUsage().heapUsed / 1e6).toFixed(0)} MB`);
        const running = [...conn.db.matchState.iter()].filter((m) => m.status.tag === "Running");
        console.log(`running matches: ${running.length}`);

        conn.db.auction.onInsert((_c, a) => {
          if (a.status.tag !== "Open") return;
          const m = conn.db.matchState.id.find(a.matchId);
          if (!m) return;
          const participants = [...conn.db.matchParticipant.iter()]
            .filter((p) => p.matchId === a.matchId)
            .map((p) => ({ botId: p.botId, balance: Number(p.balance), score: Number(p.score) }));
          if (participants.length === 0) return;
          // Pretend to be the first participant, with an empty rack (we
          // can't see their tiles); this checks the plumbing and timing.
          const s = performance.now();
          const view = buildView({
            myBotId: participants[0]!.botId, matchId: a.matchId, letter: a.letter,
            auctionsLeft: m.bagTotal, firstPrice: m.auctionType.tag === "FirstPrice",
            rack: new Map(), participants, openLetters: [a.letter],
            results: [...conn.db.auctionResult.iter()].filter((r) => r.matchId === a.matchId),
            plays: [...conn.db.wordPlay.iter()].filter((w) => w.matchId === a.matchId),
          }, lexicon);
          if (!view) return;
          const bid = STRATEGY.bid(view);
          maxDecisionMs = Math.max(maxDecisionMs, performance.now() - s);
          auctions++;
          if (auctions <= 5 || m.bagTotal === 0) {
            console.log(`match ${a.matchId} '${a.letter}': ${m.bagTotal} left, ${view.history.length} closed, unseen ${view.unseenTotal}, would bid ${bid}`);
          }
        });
        setTimeout(() => {
          console.log(`watched ${auctions} live auctions; slowest view+bid ${maxDecisionMs.toFixed(1)} ms; heap ${(process.memoryUsage().heapUsed / 1e6).toFixed(0)} MB`);
          conn.disconnect();
          process.exit(0);
        }, SECONDS * 1000);
      },
      (msg) => {
        console.error(msg);
        process.exit(1);
      },
    );
  })
  .onConnectError((_c, err) => {
    console.error("connect error:", err.message);
    process.exit(1);
  })
  .build();
