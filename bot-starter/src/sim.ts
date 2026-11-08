// Offline match simulator mirroring spacetimedb/src/game.ts:
//  - 98-tile bag (no blanks), 5-tile hidden starting racks, 100 balance
//  - one auction per drawn tile; bids <= balance; positive bids only
//  - ties broken randomly (shuffle, then stable sort by amount)
//  - Vickrey: winner pays the runner-up's bid, or the reserve (1) alone;
//    first-price: winner pays their own bid
//  - a tile nobody bids on is discarded; the match ends when the bag empties
//  - stock sims bid by formula (+-2 jitter) and, after winning, play the
//    first (longest, then alphabetical) word of 3+ letters, once
//  - real bots play words while the match runs; they react after each
//    auction closes, so the last auction's tile can never be played by them

import {
  BAG_COUNTS,
  type Counts,
  type Lexicon,
  SLOT_VALUE,
  rewardFor,
  slotOf,
} from "./lexicon.js";
import { reconstructPublicState } from "./stateTracker.js";
import type { AuctionRecord, MatchView, Policy } from "./policy.js";

export type SimStyle = "Cheapskate" | "ValueBidder" | "Aggressive";

export type Seat =
  | { kind: "sim"; style: SimStyle }
  | { kind: "policy"; policy: Policy };

export const seatName = (s: Seat): string =>
  s.kind === "sim" ? s.style : s.policy.name;

export interface MatchOptions {
  lexicon: Lexicon;
  firstPrice: boolean;
  startingRack: number;
  startingBalance: number;
}

export interface SeatResult {
  name: string;
  score: number;
  balance: number;
  place: number; // 0 = first; bots level on score share the higher place
  words: number;
  tilesWon: number;
  tilesLeft: number;
}

export type Rng = () => number;

/** Market totals across all simulated matches (for calibration against live). */
export const MARKET = {
  sold: 0, paid: 0, top: 0, unsold: 0,
  bySlot: Array.from({ length: 26 }, () => ({ sold: 0, paid: 0 })),
};

export function mulberry32(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const intIn = (rng: Rng, lo: number, hi: number): number =>
  lo + Math.floor(rng() * (hi - lo + 1));

export function shuffle<T>(rng: Rng, xs: readonly T[]): T[] {
  const out = [...xs];
  for (let i = out.length - 1; i > 0; i--) {
    const j = intIn(rng, 0, i);
    [out[i], out[j]] = [out[j]!, out[i]!];
  }
  return out;
}

const SIM_JITTER = 2;
const RESERVE = 1;
const MAX_WORDS_PER_TURN = 30;

function simBid(style: SimStyle, slot: number, balance: number, rng: Rng): number {
  const value = SLOT_VALUE[slot]!;
  const vowel = slot === 0 || slot === 4 || slot === 8 || slot === 14 || slot === 20;
  const base =
    style === "Cheapskate" ? value - 1
    : style === "ValueBidder" ? value
    : value + (vowel ? 4 : 2);
  const jitter = intIn(rng, -SIM_JITTER, SIM_JITTER);
  return Math.max(Math.min(Math.max(base + jitter, 1), balance), 0);
}

interface Player {
  seat: Seat;
  rack: Uint8Array;
  initial: Uint8Array;
  balance: number;
  score: number;
  words: number;
  tilesWon: number;
}

function applyWord(p: Player, lexicon: Lexicon, word: string, who: string) {
  if (!lexicon.has(word)) throw new Error(`${who} played '${word}', not in the dictionary`);
  let base = 0;
  for (const c of word) {
    const s = slotOf(c);
    if (p.rack[s]! === 0) throw new Error(`${who} played '${word}' without the letters`);
    p.rack[s]!--;
    base += SLOT_VALUE[s]!;
  }
  const reward = rewardFor(base, word.length);
  p.balance += reward;
  p.score += reward;
  p.words++;
}

export function runMatch(seats: Seat[], rng: Rng, opt: MatchOptions): SeatResult[] {
  const bag: number[] = [];
  BAG_COUNTS.forEach((n, s) => {
    for (let i = 0; i < n; i++) bag.push(s);
  });
  const draw = () => bag.splice(intIn(rng, 0, bag.length - 1), 1)[0]!;
  const auctioned = new Uint8Array(26);
  const publicPlays: { botId: bigint; word: string }[] = [];
  const history: { slot: number; paid: number; winner: Player | null }[] = [];

  const players: Player[] = seats.map((seat) => ({
    seat,
    rack: new Uint8Array(26),
    initial: new Uint8Array(26),
    balance: opt.startingBalance,
    score: 0,
    words: 0,
    tilesWon: 0,
  }));
  for (const p of players) {
    for (let i = 0; i < opt.startingRack; i++) {
      const s = draw();
      p.rack[s]!++;
      p.initial[s]!++;
    }
  }

  const viewFor = (p: Player, letter: string, auctionsLeft: number): MatchView => {
    const unseen = new Uint8Array(26);
    let unseenTotal = 0;
    for (let s = 0; s < 26; s++) {
      const n = Math.max(0, BAG_COUNTS[s]! - auctioned[s]! - p.initial[s]!);
      unseen[s] = n;
      unseenTotal += n;
    }
    const tracked = reconstructPublicState({
      myBotId: BigInt(players.indexOf(p)), matchId: 0n, startingRackSize: opt.startingRack,
      letter, auctionsLeft, firstPrice: opt.firstPrice,
      rack: new Map(Array.from(p.rack, (n, s) => [String.fromCharCode(65 + s), n] as [string, number])),
      participants: players.map((q, i) => ({ botId: BigInt(i), balance: q.balance, score: q.score })),
      results: history.map((h, i) => ({ auctionId: BigInt(i), letter: String.fromCharCode(65 + h.slot),
        paid: BigInt(h.paid), winnerBotId: h.winner ? BigInt(players.indexOf(h.winner)) : undefined })),
      plays: publicPlays, openLetters: letter ? [letter] : [String.fromCharCode(65 + currentSlot)],
    });
    return {
      letter,
      auctionsLeft,
      balance: p.balance,
      score: p.score,
      rack: new Uint8Array(p.rack) as Counts,
      opponents: tracked.opponents,
      remainingBagEstimate: tracked.remainingEstimate,
      unseen,
      unseenTotal,
      firstPrice: opt.firstPrice,
      history: history.map((h): AuctionRecord => ({ slot: h.slot, paid: h.paid, mine: h.winner === p })),
      lexicon: opt.lexicon,
    };
  };

  let currentSlot = 0;
  while (bag.length > 0) {
    const slot = draw();
    currentSlot = slot;
    const letter = String.fromCharCode(65 + slot);
    auctioned[slot]!++;
    const auctionsLeft = bag.length;

    // Real bots act when the auction opens: words first, then a bid.
    for (const p of players) {
      if (p.seat.kind !== "policy") continue;
      for (let k = 0; k < MAX_WORDS_PER_TURN; k++) {
        const word = p.seat.policy.play(viewFor(p, "", auctionsLeft));
        if (!word) break;
        applyWord(p, opt.lexicon, word, p.seat.policy.name);
        publicPlays.push({ botId: BigInt(players.indexOf(p)), word });
      }
    }

    const bids = players.map((p) => {
      let amount: number;
      if (p.seat.kind === "sim") {
        amount = simBid(p.seat.style, slot, p.balance, rng);
      } else {
        amount = p.seat.policy.bid(viewFor(p, letter, auctionsLeft));
        if (!Number.isInteger(amount) || amount < 0 || amount > p.balance) {
          throw new Error(`${p.seat.policy.name} bid ${amount} with balance ${p.balance}`);
        }
      }
      return { p, amount };
    });
    const ranked = shuffle(rng, bids)
      .filter((b) => b.amount > 0)
      .sort((a, b) => b.amount - a.amount);
    const [first, second] = ranked;
    if (!first) {
      history.push({ slot, paid: 0, winner: null });
      MARKET.unsold++;
      continue;
    }
    const paid = opt.firstPrice ? first.amount
      : second ? second.amount : Math.min(RESERVE, first.amount);
    const w = first.p;
    if (w.balance < paid) {
      history.push({ slot, paid: 0, winner: null });
      continue;
    }
    history.push({ slot, paid, winner: w });
    MARKET.sold++;
    MARKET.paid += paid;
    MARKET.top += first.amount;
    MARKET.bySlot[slot]!.sold++;
    MARKET.bySlot[slot]!.paid += paid;
    w.balance -= paid;
    w.rack[slot]!++;
    w.tilesWon++;
    if (w.seat.kind === "sim") {
      const i = opt.lexicon.first(w.rack, 3);
      if (i >= 0) {
        const word = opt.lexicon.words[i]!;
        applyWord(w, opt.lexicon, word, w.seat.style);
        publicPlays.push({ botId: BigInt(players.indexOf(w)), word });
      }
    }
  }

  return players.map((p) => {
    let left = 0;
    for (let s = 0; s < 26; s++) left += p.rack[s]!;
    return {
      name: seatName(p.seat),
      score: p.score,
      balance: p.balance,
      place: players.filter((q) => q.score > p.score).length,
      words: p.words,
      tilesWon: p.tilesWon,
      tilesLeft: left,
    };
  });
}
