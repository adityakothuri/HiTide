// Strategy B: value letters by how much they improve the rack's prospects.
//
// The rack's potential is the best expected reward over dictionary words it
// can spell now or is close to spelling: reward(word) times the chance of
// winning the missing letters before the bag runs out. A letter is worth
// potential(rack + letter) - potential(rack) points, converted to a bid with
// a spend rate that rises as auctions run out (leftover balance is worth
// nothing at the end). Words are played when holding doesn't promise more.

import { type Counts, type Lexicon, LETTER_VALUE, totalOf } from "../lexicon.js";
import type { MatchView, Policy } from "../policy.js";

export interface PlannerParams {
  maxDeficit: number;   // letters a target word may still be missing
  winRate: number;      // chance of winning a given needed letter if it shows
  pointsToBid: number;  // currency bid per point of marginal potential
  faceFloor: number;    // currency bid per face point regardless of fit
  flatFloor: number;    // flat currency added to every bid
  spendTarget: number;  // balance per remaining auction considered "normal"
  spendMin: number;     // bid multiplier when poor
  spendMax: number;     // bid multiplier when rich
  maxBidShare: number;  // never bid more than this share of balance (before last)
  holdMargin: number;   // hold only if holding beats playing by this factor
  lastAuctionAllIn: number; // 1: bid whole balance on the final auction
  minTargetLength: number;  // incomplete targets must be at least this long
  firstPriceShade: number;  // bid multiplier when the winner pays their own bid
  // Strategy C (adaptive) components; 0 turns each off.
  marketWeight: number;     // 0..1: blend spendTarget toward recent clearing prices
  marketWindow: number;     // how many recent paid auctions to average
  behindBoost: number;      // extra bid factor when trailing the leader by 50+
  oppBalanceCap: number;    // 1: in first-price, never bid above richest rival + 1
  /** >0: choose the word maximizing reward + leftover potential among the
   *  top N playable words, and plan the final cash-in as a set of words. */
  playSearch: number;
  /** Longest word to aim for or play before the final auction (7 = the
   *  3x multiplier's threshold; longer words spend tiles for little). */
  maxWordLength: number;
}

export const PLANNER_PARAMS: PlannerParams = {
  maxDeficit: 2,
  winRate: 0.7,
  pointsToBid: 1.0,
  faceFloor: 1.0,
  flatFloor: 1,
  spendTarget: 4,
  spendMin: 0.6,
  spendMax: 3,
  maxBidShare: 0.6,
  holdMargin: 1.0,
  lastAuctionAllIn: 1,
  minTargetLength: 5,
  firstPriceShade: 1,
  marketWeight: 0,
  marketWindow: 12,
  behindBoost: 0,
  oppBalanceCap: 1,
  playSearch: 0,
  maxWordLength: 99,
};

function popcount(x: number): number {
  x -= (x >>> 1) & 0x55555555;
  x = (x & 0x33333333) + ((x >>> 2) & 0x33333333);
  return (((x + (x >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24;
}

/** Chance of acquiring one more copy of each letter, by slot. */
function acquireOdds(v: MatchView, p: PlannerParams): Float64Array {
  const odds = new Float64Array(26);
  const share = v.unseenTotal > 0 ? Math.min(1, v.auctionsLeft / v.unseenTotal) : 0;
  for (let s = 0; s < 26; s++) {
    const shows = 1 - (1 - share) ** v.unseen[s]!;
    odds[s] = p.winRate * shows;
  }
  return odds;
}

/**
 * Potential of `rack`, and of `rack` plus one `extra` letter (slot, or -1),
 * in one pass over the dictionary.
 */
export function potentials(
  lex: Lexicon,
  rack: Counts,
  extra: number,
  odds: Float64Array,
  p: PlannerParams,
): [number, number] {
  const tiles = totalOf(rack);
  let rackMask = 0;
  for (let s = 0; s < 26; s++) if (rack[s]! > 0) rackMask |= 1 << s;
  const plusMask = extra >= 0 ? rackMask | (1 << extra) : rackMask;
  // Every surviving need is at most maxDeficit + 1. Evaluate each power
  // once, using the same exponentiation as the original per-word loop.
  const stride = Math.max(1, Math.min(256, Math.floor(p.maxDeficit + 1) + 1));
  const powers = new Float64Array(26 * stride);
  let boundedOdds = true;
  for (let s = 0; s < 26; s++) {
    if (!(odds[s]! >= 0 && odds[s]! <= 1)) boundedOdds = false;
    for (let n = 1; n < stride; n++) powers[s * stride + n] = odds[s]! ** n;
  }
  let best = 0;
  let bestPlus = 0;
  const deficitLimit = p.maxDeficit + (extra >= 0 ? 1 : 0);
  const start = lex.startAt(Math.min(tiles + 1 + p.maxDeficit, p.maxWordLength));
  for (let i = start; i < lex.words.length; i++) {
    const len = lex.length[i]!;
    const missingKinds = popcount(lex.mask[i]! & ~plusMask);
    if (missingKinds > p.maxDeficit) continue;
    const reward = lex.reward[i]!;
    // Without an extra, the original bestPlus stays zero during the scan.
    // For probabilities in [0, 1], reward is also a safe upper bound on the
    // base value. Keep the original pruning for odds outside that domain.
    if (reward <= best && (reward <= bestPlus || (extra < 0 && boundedOdds))) continue;
    const base = i * 26;
    const end = lex.slotOffsets[i + 1]!;
    // Short targets can contribute only when already complete (or completed
    // by the extra); their allowed deficit is independent of maxDeficit.
    const limit = len < p.minTargetLength ? Math.min(deficitLimit, extra >= 0 ? 1 : 0) : deficitLimit;
    let deficit = 0;
    let weight = 1;
    let weightPlus = 1; // as `weight`, but one copy of `extra` already held
    let extraNeeded = false;
    // Keep alphabetical multiplication order for bit-for-bit identical odds.
    for (let j = lex.slotOffsets[i]!; j < end; j++) {
      const s = lex.slots[j]!;
      const need = lex.counts[base + s]! - rack[s]!;
      if (need <= 0) continue;
      deficit += need;
      // Counts are nonnegative: a partial deficit cannot decrease. With no
      // extra letter, even maxDeficit + 1 cannot contribute to either result.
      if (deficit > limit) break;
      const w = powers[s * stride + need]!;
      weight *= w;
      if (s === extra) {
        extraNeeded = true;
        weightPlus *= need > 1 ? powers[s * stride + need - 1]! : 1;
      } else if (extra >= 0) {
        weightPlus *= w;
      }
    }
    if (deficit > limit) continue;
    if (deficit <= p.maxDeficit && (deficit === 0 || len >= p.minTargetLength)) {
      const value = reward * weight;
      if (value > best) best = value;
    }
    if (extra >= 0) {
      // With the extra letter in hand, one fewer copy of it is missing.
      const d2 = extraNeeded ? deficit - 1 : deficit;
      if (d2 <= p.maxDeficit && (d2 === 0 || len >= p.minTargetLength)) {
        const value = reward * weightPlus;
        if (value > bestPlus) bestPlus = value;
      }
    }
  }
  if (extra < 0) bestPlus = best;
  return [best, Math.max(best, bestPlus)];
}

/** Balance per remaining auction that counts as a normal spend rate. */
function spendTargetFor(v: MatchView, p: PlannerParams): number {
  if (p.marketWeight <= 0) return p.spendTarget;
  let sum = 0;
  let n = 0;
  for (let i = v.history.length - 1; i >= 0 && n < p.marketWindow; i--) {
    const h = v.history[i]!;
    if (h.paid <= 0) continue;
    sum += h.paid;
    n++;
  }
  if (n < 3) return p.spendTarget;
  return Math.max(0.5, (1 - p.marketWeight) * p.spendTarget + p.marketWeight * (sum / n));
}

export function planner(o: Partial<PlannerParams> = {}, name = "Planner"): Policy {
  const p: PlannerParams = { ...PLANNER_PARAMS, ...o };
  return {
    name,
    bid(v) {
      const balance = Math.floor(v.balance);
      if (balance <= 0) return 0;
      if (v.auctionsLeft === 0 && p.lastAuctionAllIn >= 1) {
        if (!v.firstPrice) return balance; // money is worthless after this
        const richest = Math.max(0, ...v.opponents.map((o) => o.balance));
        return Math.min(balance, richest + 1);
      }
      const slot = v.letter.charCodeAt(0) - 65;
      const odds = acquireOdds(v, p);
      const [now, withLetter] = potentials(v.lexicon, v.rack, slot, odds, p);
      const marginal = Math.max(0, withLetter - now);
      const face = LETTER_VALUE[v.letter] ?? 1;
      let worth = p.pointsToBid * marginal + p.faceFloor * face + p.flatFloor;
      const perAuction = balance / (v.auctionsLeft + 1);
      const spend = Math.min(p.spendMax, Math.max(p.spendMin, perAuction / spendTargetFor(v, p)));
      worth *= spend;
      if (p.behindBoost > 0) {
        const leader = Math.max(0, ...v.opponents.map((o) => o.score));
        const gap = leader - v.score;
        if (gap > 0) worth *= 1 + p.behindBoost * Math.min(1, gap / 50);
      }
      if (v.firstPrice) worth *= p.firstPriceShade;
      let cap = Math.max(1, Math.floor(balance * p.maxBidShare));
      if (v.firstPrice && p.oppBalanceCap >= 1) {
        // Paying our own bid: anything above the richest rival's balance
        // (+1 to beat a tie) is wasted.
        const richest = Math.max(0, ...v.opponents.map((o) => o.balance));
        cap = Math.min(cap, richest + 1);
      }
      return Math.max(0, Math.min(balance, cap, Math.round(worth)));
    },
    play(v) {
      if (p.playSearch > 0) return searchPlay(v, p);
      const lex = v.lexicon;
      if (v.auctionsLeft === 0) {
        const last = lex.best(v.rack, 2); // last chance: cash in, any length
        return last < 0 ? null : lex.words[last]!;
      }
      const i = lex.best(v.rack, 2, p.maxWordLength);
      if (i < 0) return null;
      const odds = acquireOdds(v, p);
      const [hold] = potentials(lex, v.rack, -1, odds, p);
      const word = lex.words[i]!;
      const rest = new Uint8Array(v.rack);
      for (const c of word) rest[c.charCodeAt(0) - 65]!--;
      const [after] = potentials(lex, rest, -1, odds, p);
      return lex.reward[i]! + after >= hold * p.holdMargin ? word : null;
    },
  };
}

function minus(rack: Counts, lex: Lexicon, i: number): Uint8Array {
  const out = new Uint8Array(rack);
  const base = i * 26;
  for (let s = 0; s < 26; s++) out[s]! -= lex.counts[base + s]!;
  return out;
}

/** Best total reward from disjoint words among `cands` (indices spellable
 *  from `rack`), up to `depth` words. Returns [total, first word or -1]. */
function bestSet(lex: Lexicon, rack: Uint8Array, cands: number[], from: number, depth: number): [number, number] {
  if (depth === 0) return [0, -1];
  let best = 0;
  let first = -1;
  for (let k = from; k < cands.length; k++) {
    const i = cands[k]!;
    if (!lex.spells(i, rack)) continue;
    // Rewards are sorted, so even k words of this reward can't beat best.
    if (lex.reward[i]! * depth <= best) break;
    const [rest] = bestSet(lex, minus(rack, lex, i), cands, k + 1, depth - 1);
    const total = lex.reward[i]! + rest;
    if (total > best) {
      best = total;
      first = i;
    }
  }
  return [best, first];
}

function searchPlay(v: MatchView, p: PlannerParams): string | null {
  const lex = v.lexicon;
  if (v.auctionsLeft === 0) {
    // Last chance: the best set of words from the whole rack.
    const cands = lex.topSpellable(v.rack, 2, 60);
    if (cands.length === 0) return null;
    const [, first] = bestSet(lex, new Uint8Array(v.rack), cands, 0, 4);
    return first < 0 ? null : lex.words[first]!;
  }
  const cands = lex.topSpellable(v.rack, 2, p.playSearch);
  if (cands.length === 0) return null;
  const odds = acquireOdds(v, p);
  const [hold] = potentials(lex, v.rack, -1, odds, p);
  let bestI = -1;
  let bestValue = -1;
  for (const i of cands) {
    const [after] = potentials(lex, minus(v.rack, lex, i), -1, odds, p);
    const value = lex.reward[i]! + after;
    if (value > bestValue) {
      bestValue = value;
      bestI = i;
    }
  }
  return bestValue >= hold * p.holdMargin ? lex.words[bestI]! : null;
}
