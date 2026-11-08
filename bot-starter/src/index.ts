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
import { writeScoutHeartbeat, applyScoutingBid, scoutingWord } from "./scouting.js";
import { clonePolicy, type CloneModel } from "./clonePolicy.js";
import type { Policy } from "./policy.js";

const HOST = process.env.STDB_HOST ?? "https://maincloud.spacetimedb.com";
const DB_NAME = process.env.STDB_DB ?? "scrabblebot";
const BOT_NAME = process.env.BOT_NAME ?? "larper";
const BOT_TOKEN = process.env.BOT_TOKEN; // from the website, first run only
const BOT_NONCE = process.env.BOT_NONCE; // from the CLI, first run only
const TOURNAMENT_ID = process.env.TOURNAMENT_ID;
const TOKEN_PATH = path.join(process.cwd(), `.token-${BOT_NAME}`);
const QUIET = process.env.QUIET === "1";
const MAX_WORDS_PER_TURN = 1; // Wait for each reducer before choosing another word.
// Scoutroom fleet: a clone runs a fitted model instead of STRATEGY, logs each
// finished match, and can be drained (finish the current match, then exit).
const CLONE_MODEL_PATH = process.env.CLONE_MODEL_PATH;
const RESULTS_PATH = process.env.RESULTS_PATH;
const CONTROL_PATH = process.env.CONTROL_PATH;
// Clone models hot-reload between matches, so a bot can be retrained without
// a restart and without starting a new rated version.
let modelMtime = 0, modelFittedAt: string | null = null;
function loadClone(): Policy {
  const model = JSON.parse(fs.readFileSync(CLONE_MODEL_PATH!, "utf8")) as CloneModel;
  const policy = clonePolicy(model);
  modelMtime = fs.statSync(CLONE_MODEL_PATH!).mtimeMs; modelFittedAt = model.fittedAt;
  return policy;
}
let POLICY: Policy = CLONE_MODEL_PATH ? loadClone() : STRATEGY;
function reloadCloneIfChanged() {
  if (!CLONE_MODEL_PATH) return;
  try {
    if (fs.statSync(CLONE_MODEL_PATH).mtimeMs === modelMtime) return;
    POLICY = loadClone();
    console.log(`[${BOT_NAME}] reloaded clone model fitted ${modelFittedAt}`);
  } catch (e) { console.warn(`[${BOT_NAME}] model reload failed, keeping current model: ${e}`); }
}
const bidFor = (view: Parameters<Policy["bid"]>[0]) => CLONE_MODEL_PATH ? POLICY.bid(view) : applyScoutingBid(view, POLICY.bid(view));
const wordFor = (view: Parameters<Policy["play"]>[0]) => CLONE_MODEL_PATH ? POLICY.play(view) : scoutingWord(view, () => POLICY.play(view));
let matchesFinished = 0;
let draining = false;
// Optional deliberate bid delay (ms), set from Scoutroom. Bids are private on the
// server, so a later bid gains nothing; a bid after the window closes is lost.
let bidDelayMs = 0;
const MAX_BID_DELAY_MS = 900;
function readControl() {
  if (!CONTROL_PATH) return;
  try {
    const control = JSON.parse(fs.readFileSync(CONTROL_PATH, "utf8"));
    draining = control.drain === true;
    const delay = Number(control.bidDelayMs ?? 0);
    bidDelayMs = Number.isFinite(delay) ? Math.max(0, Math.min(MAX_BID_DELAY_MS, Math.round(delay))) : 0;
  } catch { draining = false; bidDelayMs = 0; }
}

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
let liveConnection: DbConnection | null = null;
function liveMatch(conn: DbConnection | null) {
  if (!conn || myBotId === null) return null;
  const id = runningMatches(conn)[0];
  if (id === undefined) return null;
  const m = conn.db.matchState.id.find(id);
  const table = participantsOf(conn, id);
  const me = table.find(p => p.botId === myBotId);
  if (!m || !me) return null;
  return { matchId: String(id), score: Number(me.score), balance: Number(me.balance), auctionsLeft: m.bagTotal, players: table.length, place: 1 + table.filter(p => p.score > me.score).length };
}
const runtimeTimer = setInterval(() => {
  readControl();
  const running = liveConnection ? runningMatches(liveConnection) : [];
  if (running.length === 0) reloadCloneIfChanged();
  writeScoutHeartbeat({ botName: BOT_NAME, botId: myBotId?.toString() ?? null, strategy: POLICY.name, connected: liveConnection?.isActive ?? false, runningMatches: running.map(String), match: liveMatch(liveConnection), matchesFinished, draining, supportsDrain: true, modelFittedAt, lobbyWait, onePerLobby: ONE_PER_LOBBY, lateRate: lateRate(), bidsSampled: bidLate.length, bidDelayMs });
  if (draining && running.length === 0 && myBotId !== null) { console.log(`[${BOT_NAME}] drained; exiting`); process.exit(0); }
}, 2000);
runtimeTimer.unref();

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

// Per-match indexes: the cache holds ~200 recent matches, so full scans on every
// event made runners fall seconds behind under load and bids missed the 1s window.
const participantsOf = (conn: DbConnection, matchId: bigint) => [...conn.db.matchParticipant.mpByMatch.filter(matchId)];

function refreshMyMatches(conn: DbConnection) {
  if (myBotId === null) return;
  for (const p of conn.db.matchParticipant.mpByBot.filter(myBotId)) myMatches.add(String(p.matchId));
}

function runningMatches(conn: DbConnection): bigint[] {
  if (myBotId === null) return [];
  const out: bigint[] = [];
  for (const p of conn.db.matchParticipant.mpByBot.filter(myBotId)) {
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
  const participants = participantsOf(conn, matchId).map(p => ({ botId: p.botId, balance: Number(p.balance), score: Number(p.score) }));
  const openLetters: string[] = [];
  for (const a of conn.db.auction.auctionByMatch.filter(matchId)) {
    if (a.status.tag === "Open") openLetters.push(a.letter);
  }
  const results = [...conn.db.auctionResult.resultByMatch.filter(matchId)];
  const plays = [...conn.db.wordPlay.playByMatch.filter(matchId)];
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
    const word = wordFor(view);
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
// Rolling record of recent bids: true = arrived after the auction closed.
const bidLate: boolean[] = [];
const BID_WINDOW = 100;
function noteBid(late: boolean) { bidLate.push(late); if (bidLate.length > BID_WINDOW) bidLate.shift(); }
const lateRate = () => bidLate.length ? bidLate.filter(Boolean).length / bidLate.length : null;

function tryBid(conn: DbConnection, auctionId: bigint, matchId: bigint, letter: string) {
  if (!isMine(matchId)) return;
  const auction = conn.db.auction.id.find(auctionId);
  if (auction && Number(auction.closesAt.microsSinceUnixEpoch / 1000n) <= Date.now()) { noteBid(true); return; } // already closed
  const snap = snapshot(conn, matchId, letter);
  if (!snap) return;
  const view = buildView(snap, LEXICON);
  if (!view) return;
  const raw = bidFor(view);
  const amount = Math.max(0, Math.min(Math.floor(view.balance), Math.floor(raw)));
  const key = String(auctionId);
  const previous = lastBid.get(key);
  if (previous === amount || (previous === undefined && amount === 0)) return;
  lastBid.set(key, amount);
  const send = () => {
    if (lastBid.get(key) !== amount) return; // superseded by a newer decision
    conn.reducers
      .submitBid({ auctionId, amount: BigInt(amount) })
      .then(() => noteBid(false))
      .catch(err => { noteBid(/closed|expired/i.test(String(err instanceof Error ? err.message : err))); logFailure(`bid on auction ${auctionId}`)(err); });
  };
  if (bidDelayMs > 0) setTimeout(send, bidDelayMs); else send();
  say(`bid ${amount} on '${letter}' (match ${matchId}, auction ${auctionId}, ${snap.auctionsLeft} left)`);
}

function rebidOpenAuctions(conn: DbConnection, matchId: bigint) {
  if (!isMine(matchId)) return;
  for (const a of conn.db.auction.auctionByMatch.filter(matchId)) {
    if (a.status.tag === "Open") tryBid(conn, a.id, a.matchId, a.letter);
  }
}

function onConnect(conn: DbConnection, identity: Identity, token: string) {
  liveConnection = conn;
  myIdentity = identity;
  saveToken(token);
  console.log(`[${BOT_NAME}] connected as ${identity.toHexString()} (strategy ${POLICY.name})`);

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
      for (const p of conn.db.matchParticipant.mpByMatch.filter(a.matchId)) {
        if (p.botId === myBotId) myMatches.add(String(a.matchId));
      }
    }
    if (!isMine(a.matchId)) return;
    // Bid first: the auction closes in ~1s. A word that changes cash triggers a rebid.
    tryBid(conn, a.id, a.matchId, a.letter);
    tryPlayWords(conn, a.matchId);
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

  // Waiting for a teammate-free lobby: retry whenever the lobby changes.
  for (const l of conn.db.lobby.iter()) if (l.id > newestLobbyId) newestLobbyId = l.id; // once, at connect
  conn.db.lobby.onInsert((_ctx, l) => { if (l.id > newestLobbyId) newestLobbyId = l.id; });
  const retryLobby = () => { if (lobbyWait && myBotId !== null) joinLobby(conn); };
  conn.db.lobby.onInsert(retryLobby);
  conn.db.lobby.onUpdate(retryLobby);
  conn.db.lobbyMember.onInsert(retryLobby);
  conn.db.lobbyMember.onDelete(retryLobby);
  setInterval(() => { if (liveConnection && myBotId !== null && runningMatches(liveConnection).length === 0) joinLobby(liveConnection); }, 5000).unref();

  // When a match this bot was in ends, hop back into the lobby.
  conn.db.matchState.onUpdate((_ctx, old, neu) => {
    if (myBotId === null) return;
    if (old.status.tag !== "Ended" && neu.status.tag === "Ended") {
      const me = participantsOf(conn, neu.id).find(
        (p) => p.matchId === neu.id && p.botId === myBotId,
      );
      if (me) {
        const table = participantsOf(conn, neu.id);
        recordResult(neu.id, me, table);
        lastWordState.delete(String(neu.id));
        readControl();
        if (draining) { console.log(`[${BOT_NAME}] match ${neu.id} ended with score ${me.score}; drained, exiting`); process.exit(0); }
        console.log(`[${BOT_NAME}] match ${neu.id} ended with score ${me.score}; rejoining lobby`);
        joinLobby(conn);
      }
    }
  });
}

function recordResult(matchId: bigint, me: { score: bigint | number; balance: bigint | number }, table: { botId: bigint; score: bigint | number }[]) {
  matchesFinished++;
  if (!RESULTS_PATH) return;
  const score = Number(me.score), top = Math.max(...table.map(p => Number(p.score)));
  const result = { matchId: String(matchId), endedAt: new Date().toISOString(), score, balance: Number(me.balance), players: table.length,
    place: 1 + table.filter(p => Number(p.score) > score).length, won: score === top, tiedFirst: score === top && table.filter(p => Number(p.score) === top).length > 1 };
  try { fs.appendFileSync(RESULTS_PATH, JSON.stringify(result) + "\n"); } catch (e) { console.warn(`[${BOT_NAME}] result log failed: ${e}`); }
}

// One team bot per lobby: every match is against outside opponents, so results
// (and ratings) measure the strategy instead of our bots trading points. The
// server has a single open lobby; a bot waits while a teammate is in it.
const TEAM_PREFIX = process.env.TEAM_PREFIX ?? "Pegasus";
const ONE_PER_LOBBY = process.env.ONE_PER_LOBBY !== "0";
const LOBBY_LOCKS = path.join(process.cwd(), "bench", "results", "lobby-locks");
let lobbyWait: { lobbyId: string; teammate: string } | null = null;
let newestLobbyId = 0n; // kept current by lobby inserts instead of scanning ~27k rows

function teammateInLobby(conn: DbConnection, lobbyId: bigint): string | null {
  for (const m of conn.db.lobbyMember.lmByLobby.filter(lobbyId)) {
    if (m.botId === myBotId) continue;
    const name = conn.db.bot.id.find(m.botId)?.name ?? "";
    if (name.startsWith(TEAM_PREFIX)) return name;
  }
  return null;
}

/** Same-machine tie-break: only one local bot may claim a given lobby. */
function claimLobby(key: string): boolean {
  try {
    fs.mkdirSync(LOBBY_LOCKS, { recursive: true });
    fs.writeFileSync(path.join(LOBBY_LOCKS, key), BOT_NAME, { flag: "wx" });
    return true;
  } catch {
    try { return fs.readFileSync(path.join(LOBBY_LOCKS, key), "utf8") === BOT_NAME; } catch { return false; }
  }
}

function joinLobby(conn: DbConnection) {
  readControl();
  if (draining) return;
  if (myBotId === null) return;
  if (runningMatches(conn).length > 0) return;
  const openLobby = [...conn.db.lobby.lobbyByStatus.filter({ tag: "Open" })][0];
  const alreadyIn =
    openLobby !== undefined &&
    [...conn.db.lobbyMember.lmByLobby.filter(openLobby.id)].some((lm) => lm.botId === myBotId);
  if (alreadyIn) { lobbyWait = null; return; }
  if (ONE_PER_LOBBY) {
    const teammate = openLobby ? teammateInLobby(conn, openLobby.id) : null;
    // With no open lobby, joining creates the next one: key the claim by the newest lobby id.
    const key = openLobby ? `lobby-${openLobby.id}` : `after-${newestLobbyId}`;
    if (teammate || !claimLobby(key)) {
      const id = String(openLobby?.id ?? `next`), who = teammate ?? "a local teammate";
      if (lobbyWait?.lobbyId !== id) console.log(`[${BOT_NAME}] ${who} is in lobby ${id}; waiting for the next lobby`);
      lobbyWait = { lobbyId: id, teammate: who };
      return;
    }
  }
  lobbyWait = null;
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
