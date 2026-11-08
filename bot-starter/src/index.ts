// ScrabbleBot bot.
//
// First run, with a token from the website:
//   On your team's page, click "Generate token", then run
//   `BOT_NAME=<name> BOT_TOKEN=<token> npm start`.
//
// Or with a nonce from the CLI:
//   1. `spacetime call scrabblebot mint_credential_nonce`
//      `spacetime sql 'SELECT code FROM my_nonces ORDER BY expires_at DESC'`
//   2. `BOT_NAME=<name> BOT_NONCE=<code> npm start`
//      The bot connects fresh and redeems the nonce.
//
// Either way the bot saves its token to .token-<BOT_NAME>, so later runs
// need only `BOT_NAME=<name> npm start`.
//
// Entering a tournament: `BOT_NAME=<name> TOURNAMENT_ID=<id> npm start`
// registers the bot for that tournament when it connects. Only the bot
// itself can register, so this has to come from the bot's process.
//
// The strategy lives in ./src/strategy.ts (see bench/ for how it was chosen).

import {
  DbConnection,
  type EventContext,
  type ErrorContext,
} from "./module_bindings/index.js";
import { Identity } from "spacetimedb";
import * as fs from "node:fs";
import * as path from "node:path";
import { Lexicon, slotOf, wordReward } from "./lexicon.js";
import { type LiveSnapshot, buildView } from "./live.js";
import { STRATEGY } from "./strategy.js";
import { subscribeForBot } from "./subscribe.js";

const HOST = process.env.STDB_HOST ?? "https://maincloud.spacetimedb.com";
const DB_NAME = process.env.STDB_DB ?? "scrabblebot";
const BOT_NAME = process.env.BOT_NAME ?? "bot";
const BOT_TOKEN = process.env.BOT_TOKEN; // from the website, first run only
const BOT_NONCE = process.env.BOT_NONCE; // from the CLI, first run only
const TOURNAMENT_ID = process.env.TOURNAMENT_ID;
const TOKEN_PATH = path.join(process.cwd(), `.token-${BOT_NAME}`);
const QUIET = process.env.QUIET === "1";
const MAX_WORDS_PER_TURN = 1; // Wait for each reducer before choosing another word.

function loadToken(): string | undefined {
  try {
    return fs.readFileSync(TOKEN_PATH, "utf8").trim() || undefined;
  } catch {
    return undefined;
  }
}
function saveToken(tok: string) {
  fs.writeFileSync(TOKEN_PATH, tok);
}

// The shared wordlist; the server validates words against the same list.
const dictionaryPath = path.join(
  path.dirname(new URL(import.meta.url).pathname),
  "..",
  "..",
  "spacetimedb",
  "wordlist.txt",
);
if (!fs.existsSync(dictionaryPath)) {
  console.error(`wordlist not found at ${dictionaryPath}`);
  process.exit(1);
}
const LEXICON = Lexicon.fromFile(dictionaryPath);

let myIdentity: Identity | null = null;
let myBotId: bigint | null = null;
const lastBid = new Map<string, number>(); // auction id -> amount sent
// Matches this bot plays in. The subscription carries every match on the
// server; events for other matches are ignored before doing any work, or
// the bot falls behind the event stream and its bids arrive late.
const myMatches = new Set<string>();
const isMine = (matchId: bigint) => myMatches.has(String(matchId));
const checkedMatches = new Set<string>(); // matches whose roster was scanned once
const lastWordState = new Map<string, string>(); // match id -> rack+round acted on
const wordsInFlight = new Map<string, number>(); // match id -> unsettled words

const say = (msg: string) => {
  if (!QUIET) console.log(`[${BOT_NAME}] ${msg}`);
};

function resolveMyBotId(conn: DbConnection): bigint | null {
  if (!myIdentity) return null;
  const cred = conn.db.botCredential.identity.find(myIdentity);
  return cred ? cred.botId : null;
}

// A reducer call fails when the module refuses it, often for an expected
// reason: a word played just after its match ended, a bid that missed the
// auction's window. Log it and keep playing; an uncaught failure would stop
// the bot.
function logFailure(what: string) {
  return (err: unknown) =>
    console.warn(
      `[${BOT_NAME}] ${what} failed: ${err instanceof Error ? err.message : err}`,
    );
}

function refreshMyMatches(conn: DbConnection) {
  if (myBotId === null) return;
  for (const p of conn.db.matchParticipant.iter()) {
    if (p.botId === myBotId) myMatches.add(String(p.matchId));
  }
}

function runningMatches(conn: DbConnection): bigint[] {
  if (myBotId === null) return [];
  const out: bigint[] = [];
  for (const p of conn.db.matchParticipant.iter()) {
    if (p.botId !== myBotId) continue;
    const m = conn.db.matchState.id.find(p.matchId);
    if (m?.status.tag === "Running") out.push(p.matchId);
  }
  return out;
}

function snapshot(conn: DbConnection, matchId: bigint, letter: string): LiveSnapshot | null {
  if (myBotId === null) return null;
  const m = conn.db.matchState.id.find(matchId);
  if (!m || m.status.tag !== "Running") return null;
  const rack = new Map<string, number>();
  for (const h of conn.db.myRack.iter()) {
    if (h.matchId !== matchId) continue;
    rack.set(h.letter, (rack.get(h.letter) ?? 0) + h.count);
  }
  const participants = [];
  for (const p of conn.db.matchParticipant.iter()) {
    if (p.matchId !== matchId) continue;
    participants.push({ botId: p.botId, balance: Number(p.balance), score: Number(p.score) });
  }
  const openLetters: string[] = [];
  for (const a of conn.db.auction.iter()) {
    if (a.matchId === matchId && a.status.tag === "Open") openLetters.push(a.letter);
  }
  const results = [...conn.db.auctionResult.iter()].filter((r) => r.matchId === matchId);
  const plays = [...conn.db.wordPlay.iter()].filter((w) => w.matchId === matchId);
  return {
    myBotId,
    startingRackSize: m.startingRackSize,
    matchId,
    letter,
    auctionsLeft: m.bagTotal,
    firstPrice: m.auctionType.tag === "FirstPrice",
    rack,
    participants,
    openLetters,
    results,
    plays,
  };
}

function rackKey(rack: Map<string, number>): string {
  return [...rack.entries()]
    .filter(([, n]) => n > 0)
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([c, n]) => c.repeat(n))
    .join("");
}

/** Play the words the strategy wants now, one decision per rack + round. */
function tryPlayWords(conn: DbConnection, matchId: bigint) {
  if (!isMine(matchId)) return;
  const key = String(matchId);
  if ((wordsInFlight.get(key) ?? 0) > 0) return; // wait for the server
  const snap = snapshot(conn, matchId, "");
  if (!snap) return;
  const state = `${rackKey(snap.rack)}:${snap.auctionsLeft}:${snap.participants.find(p => p.botId === myBotId)?.balance}`;
  if (lastWordState.get(key) === state) return;
  lastWordState.set(key, state);
  const view = buildView(snap, LEXICON);
  if (!view) return;

  const words: string[] = [];
  for (let k = 0; k < MAX_WORDS_PER_TURN; k++) {
    const word = STRATEGY.play(view);
    if (!word) break;
    const rack = new Uint8Array(view.rack);
    let ok = LEXICON.has(word);
    for (const c of word) {
      const s = slotOf(c);
      if (rack[s]! === 0) ok = false;
      else rack[s]!--;
    }
    if (!ok) {
      console.warn(`[${BOT_NAME}] strategy chose unplayable '${word}'; skipping`);
      break;
    }
    const reward = wordReward(word);
    view.rack = rack;
    view.balance += reward;
    view.score += reward;
    words.push(word);
  }
  if (words.length === 0) return;

  wordsInFlight.set(key, words.length);
  let failed = false;
  const settle = () => {
    const left = (wordsInFlight.get(key) ?? 1) - 1;
    wordsInFlight.set(key, left);
    if (left === 0) {
      if (failed) return; // Avoid retry loops on a rejected reducer.
      lastWordState.delete(key);
      tryPlayWords(conn, matchId); // the rack may have changed meanwhile
      rebidOpenAuctions(conn, matchId);
    }
  };
  for (const word of words) {
    say(`match ${matchId}: playing '${word}' (+${wordReward(word)})`);
    conn.reducers
      .submitWord({ matchId, word })
      .catch(err => { failed = true; logFailure(`playing '${word}'`)(err); })
      .finally(settle);
  }
}

/** Bid (or re-bid, if the decision changed) on one open auction. */
function tryBid(conn: DbConnection, auctionId: bigint, matchId: bigint, letter: string) {
  if (!isMine(matchId)) return;
  const snap = snapshot(conn, matchId, letter);
  if (!snap) return;
  const view = buildView(snap, LEXICON);
  if (!view) return;
  const raw = STRATEGY.bid(view);
  const amount = Math.max(0, Math.min(Math.floor(view.balance), Math.floor(raw)));
  const key = String(auctionId);
  const previous = lastBid.get(key);
  if (previous === amount || (previous === undefined && amount === 0)) return;
  lastBid.set(key, amount);
  conn.reducers
    .submitBid({ auctionId, amount: BigInt(amount) })
    .catch(logFailure(`bid on auction ${auctionId}`));
  say(`bid ${amount} on '${letter}' (match ${matchId}, auction ${auctionId}, ${snap.auctionsLeft} left)`);
}

function rebidOpenAuctions(conn: DbConnection, matchId: bigint) {
  if (!isMine(matchId)) return;
  for (const a of conn.db.auction.iter()) {
    if (a.matchId === matchId && a.status.tag === "Open") tryBid(conn, a.id, a.matchId, a.letter);
  }
}

function onConnect(conn: DbConnection, identity: Identity, token: string) {
  myIdentity = identity;
  saveToken(token);
  console.log(`[${BOT_NAME}] connected as ${identity.toHexString()} (strategy ${STRATEGY.name})`);

  subscribeForBot(
    conn,
    () => {
      console.log(`[${BOT_NAME}] subscription applied`);

      // Resolve our bot id, possibly after claiming a nonce.
      myBotId = resolveMyBotId(conn);
      if (myBotId === null) {
        if (BOT_NONCE) {
          console.log(`[${BOT_NAME}] claiming credential with nonce…`);
          conn.reducers
            .claimCredential({ code: BOT_NONCE })
            .catch(logFailure("claiming the credential"));
          // Wait briefly for the credential to land; check again.
          setTimeout(() => {
            myBotId = resolveMyBotId(conn);
            if (myBotId === null) {
              console.error(
                `[${BOT_NAME}] couldn't claim credential. Bad / expired nonce?`,
              );
              process.exit(1);
            }
            const bot = conn.db.bot.id.find(myBotId);
            console.log(
              `[${BOT_NAME}] claimed credential for bot '${bot?.name ?? "?"}' (id ${myBotId})`,
            );
            bootstrapActivity(conn);
          }, 1000);
          return;
        } else {
          console.error(
            `[${BOT_NAME}] no BotCredential for this token. Set BOT_TOKEN or BOT_NONCE and re-run.`,
          );
          process.exit(1);
        }
      }

      const bot = conn.db.bot.id.find(myBotId);
      console.log(
        `[${BOT_NAME}] acting as bot '${bot?.name ?? "?"}' (id ${myBotId})`,
      );
      bootstrapActivity(conn);
    },
    (msg) => {
      console.error(`[${BOT_NAME}] ${msg}`);
      process.exit(1);
    },
  );

  // A new auction: cash in words first (the final auction is the last
  // chance), then bid. Bids are re-sent if a word changes our balance.
  conn.db.auction.onInsert((_ctx: EventContext, a) => {
    if (a.status.tag !== "Open" || myBotId === null) return;
    if (!isMine(a.matchId) && !checkedMatches.has(String(a.matchId))) {
      // A match's first auction can arrive before its roster callback.
      checkedMatches.add(String(a.matchId));
      for (const p of conn.db.matchParticipant.iter()) {
        if (p.matchId === a.matchId && p.botId === myBotId) myMatches.add(String(a.matchId));
      }
    }
    if (!isMine(a.matchId)) return;
    tryPlayWords(conn, a.matchId);
    tryBid(conn, a.id, a.matchId, a.letter);
  });
  const onRackChange = (matchId: bigint) => {
    tryPlayWords(conn, matchId);
    rebidOpenAuctions(conn, matchId);
  };
  conn.db.myRack.onInsert((_ctx, h) => onRackChange(h.matchId));
  conn.db.myRack.onUpdate((_ctx, _old, h) => onRackChange(h.matchId));
  conn.db.myRack.onDelete((_ctx, h) => onRackChange(h.matchId));
  conn.db.matchParticipant.onUpdate((_ctx, _old, p) => {
    if (p.botId === myBotId && isMine(p.matchId)) {
      tryPlayWords(conn, p.matchId);
      rebidOpenAuctions(conn, p.matchId);
    }
  });
  conn.db.botCredential.onInsert(() => {
    if (myBotId === null) myBotId = resolveMyBotId(conn);
  });
  conn.db.matchParticipant.onInsert((_ctx, p) => {
    if (myBotId !== null && p.botId === myBotId) myMatches.add(String(p.matchId));
  });
  conn.db.auctionResult.onInsert((_ctx, r) => {
    if (myBotId === null || !isMine(r.matchId)) return;
    lastBid.delete(String(r.auctionId));
    const winner =
      r.winnerBotId !== undefined && r.winnerBotId !== null
        ? String(r.winnerBotId)
        : "no-bid";
    if ((conn.db.matchState.id.find(r.matchId)?.bagTotal ?? 99) <= 15 || r.winnerBotId === myBotId) {
      tryPlayWords(conn, r.matchId);
    }
    say(`match ${r.matchId} auction ${r.auctionId} '${r.letter}' → bot ${winner} paid ${r.paid}`);
  });

  // When a match this bot was in ends, hop back into the lobby.
  conn.db.matchState.onUpdate((_ctx, old, neu) => {
    if (myBotId === null) return;
    if (old.status.tag !== "Ended" && neu.status.tag === "Ended") {
      const me = Array.from(conn.db.matchParticipant.iter()).find(
        (p) => p.matchId === neu.id && p.botId === myBotId,
      );
      if (me) {
        console.log(`[${BOT_NAME}] match ${neu.id} ended with score ${me.score}; rejoining lobby`);
        lastWordState.delete(String(neu.id));
        joinLobby(conn);
      }
    }
  });
}

function joinLobby(conn: DbConnection) {
  if (myBotId === null) return;
  if (runningMatches(conn).length > 0) return;
  const openLobby = Array.from(conn.db.lobby.iter()).find(
    (l) => l.status.tag === "Open",
  );
  const alreadyIn =
    openLobby !== undefined &&
    Array.from(conn.db.lobbyMember.iter()).some(
      (lm) => lm.lobbyId === openLobby.id && lm.botId === myBotId,
    );
  if (alreadyIn) return;
  console.log(`[${BOT_NAME}] joining lobby`);
  conn.reducers.joinLobby({}).catch(logFailure("joining the lobby"));
}

function bootstrapActivity(conn: DbConnection) {
  if (TOURNAMENT_ID) {
    conn.reducers
      .registerForTournament({ tournamentId: BigInt(TOURNAMENT_ID) })
      .then(() =>
        console.log(`[${BOT_NAME}] registered for tournament ${TOURNAMENT_ID}`),
      )
      .catch(logFailure(`registering for tournament ${TOURNAMENT_ID}`));
  }
  refreshMyMatches(conn);
  joinLobby(conn);
  for (const matchId of runningMatches(conn)) {
    tryPlayWords(conn, matchId);
    rebidOpenAuctions(conn, matchId);
  }
}

function main() {
  console.log(`[${BOT_NAME}] connecting to ${DB_NAME} at ${HOST}`);
  DbConnection.builder()
    .withUri(HOST)
    .withDatabaseName(DB_NAME)
    .withToken(BOT_TOKEN ?? loadToken())
    .onConnect(onConnect)
    .onConnectError((_ctx: ErrorContext, err: Error) =>
      console.error("connect error:", err.message),
    )
    .onDisconnect(() => console.log("disconnected"))
    .build();
}

main();
