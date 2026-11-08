// Builds the strategy's MatchView from the live SpacetimeDB client cache.
//
// Everything here comes from public tables plus the bot's own rack:
//  - auctionsLeft: match_state.bag_total (tiles still in the bag; the
//    current auction's tile has already been drawn)
//  - opponents' balance and score: match_participant
//  - unseen tiles: the 98-tile bag minus every tile auctioned so far minus
//    this bot's own starting rack (rebuilt as rack + played - won)

import { BAG_COUNTS, type Lexicon, countsFromMap, slotOf } from "./lexicon.js";
import { reconstructPublicState } from "./stateTracker.js";
import type { AuctionRecord, MatchView } from "./policy.js";

export interface ResultRow {
  auctionId: bigint;
  letter: string;
  winnerBotId?: bigint | null;
  paid: bigint;
}
export interface PlayRow {
  botId: bigint;
  word: string;
}

export interface LiveSnapshot {
  startingRackSize?: number;
  myBotId: bigint;
  matchId: bigint;
  letter: string; // "" when choosing words
  auctionsLeft: number;
  firstPrice: boolean;
  rack: Map<string, number>;
  participants: { botId: bigint; balance: number; score: number }[];
  /** Letters of auctions still open in this match (normally just one). */
  openLetters: string[];
  /** This match's closed auctions and word plays, from the client cache. */
  results: readonly ResultRow[];
  plays: readonly PlayRow[];
}

export function buildView(s: LiveSnapshot, lexicon: Lexicon): MatchView | null {
  const me = s.participants.find((p) => p.botId === s.myBotId);
  if (!me) return null;

  const tracked = reconstructPublicState(s);
  const rack = countsFromMap(s.rack);
  const auctioned = new Int32Array(26);
  const initial = new Int32Array(26);
  for (let i = 0; i < 26; i++) initial[i] = rack[i]!;
  const history: AuctionRecord[] = [];
  for (const r of [...s.results].sort((a, b) => (a.auctionId < b.auctionId ? -1 : 1))) {
    const slot = slotOf(r.letter);
    auctioned[slot]!++;
    const mine = r.winnerBotId !== undefined && r.winnerBotId !== null && r.winnerBotId === s.myBotId;
    if (mine) initial[slot]!--;
    const won = r.winnerBotId !== undefined && r.winnerBotId !== null;
    history.push({ slot, paid: won ? Number(r.paid) : 0, mine });
  }
  for (const c of s.openLetters) auctioned[slotOf(c)]!++;
  for (const p of s.plays) {
    if (p.botId !== s.myBotId) continue;
    for (const c of p.word) initial[slotOf(c)]!++;
  }

  const unseen = new Uint8Array(26);
  let unseenTotal = 0;
  for (let i = 0; i < 26; i++) {
    const n = Math.max(0, BAG_COUNTS[i]! - auctioned[i]! - Math.max(0, initial[i]!));
    unseen[i] = n;
    unseenTotal += n;
  }

  return {
    letter: s.letter,
    auctionsLeft: s.auctionsLeft,
    balance: me.balance,
    score: me.score,
    rack,
    opponents: tracked.opponents,
    remainingBagEstimate: tracked.remainingEstimate,
    unseen,
    unseenTotal,
    firstPrice: s.firstPrice,
    history,
    lexicon,
  };
}
