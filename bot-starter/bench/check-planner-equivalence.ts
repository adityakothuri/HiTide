// Frozen reference implementation below; intentionally keep its scan and math unchanged.
import assert from "node:assert/strict";
import { BAG_COUNTS, Lexicon } from "../src/lexicon.js";
import { planner as fastPlanner, potentials as fastPotentials } from "../src/strategies/planner.js";

// Strategy B: value letters by how much they improve the rack's prospects.
//
// The rack's potential is the best expected reward over dictionary words it
// can spell now or is close to spelling: reward(word) times the chance of
// winning the missing letters before the bag runs out. A letter is worth
// potential(rack + letter) - potential(rack) points, converted to a bid with
// a spend rate that rises as auctions run out (leftover balance is worth
// nothing at the end). Words are played when holding doesn't promise more.

import { type Counts, LETTER_VALUE, totalOf } from "../src/lexicon.js";
import type { MatchView, Policy } from "../src/policy.js";

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
  let best = 0;
  let bestPlus = 0;
  const start = lex.startAt(tiles + 1 + p.maxDeficit);
  for (let i = start; i < lex.words.length; i++) {
    const len = lex.length[i]!;
    const missingKinds = popcount(lex.mask[i]! & ~plusMask);
    if (missingKinds > p.maxDeficit) continue;
    const reward = lex.reward[i]!;
    if (reward <= bestPlus && reward <= best) continue; // can't improve either
    const base = i * 26;
    let deficit = 0;
    let weight = 1;
    let weightPlus = 1; // as `weight`, but one copy of `extra` already held
    let extraNeeded = false;
    for (let s = 0; s < 26; s++) {
      const need = lex.counts[base + s]! - rack[s]!;
      if (need <= 0) continue;
      deficit += need;
      const w = odds[s]! ** need;
      weight *= w;
      if (s === extra) {
        extraNeeded = true;
        weightPlus *= need > 1 ? odds[s]! ** (need - 1) : 1;
      } else {
        weightPlus *= w;
      }
    }
    if (deficit > p.maxDeficit + 1) continue;
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
      const lex = v.lexicon;
      const i = lex.best(v.rack, 2);
      if (i < 0) return null;
      if (v.auctionsLeft === 0) return lex.words[i]!; // last chance: cash in
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

// Reproducible cases: draw without replacement from the 98 physical tiles.
let seed = 0x9e3779b9;
function random(): number {
  seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
  return (seed >>> 0) / 0x100000000;
}
function int(n: number): number { return Math.floor(random() * n); }
function draw(bag: Uint8Array): number {
  let pick = int(totalOf(bag));
  for (let s = 0; s < 26; s++) {
    pick -= bag[s]!;
    if (pick < 0) { bag[s]!--; return s; }
  }
  throw new Error("empty bag");
}
const lex = Lexicon.fromFile(new URL("../../spacetimedb/wordlist.txt", import.meta.url));
const samples: { v: MatchView; p: PlannerParams; odds: Float64Array }[] = [];
for (let k = 0; k < 3000; k++) {
  const unseen = new Uint8Array(BAG_COUNTS);
  const rack = new Uint8Array(26);
  for (let n = int(21); n > 0; n--) rack[draw(unseen)]!++;
  const slot = draw(unseen);
  const auctionsLeft = int(68);
  // Seen tiles can include opponents' racks and previously auctioned tiles.
  const seen = int(Math.max(1, totalOf(unseen) - auctionsLeft + 1));
  for (let n = 0; n < seen; n++) draw(unseen);
  const p: PlannerParams = k % 4 === 0
    ? { ...PLANNER_PARAMS, maxDeficit: 1 + int(3) }
    : {
      ...PLANNER_PARAMS, maxDeficit: 1 + int(3), winRate: random(),
      pointsToBid: random() * 3, faceFloor: random() * 2, flatFloor: int(4),
      spendTarget: 0.5 + random() * 8, spendMin: random(), spendMax: 1 + random() * 4,
      maxBidShare: random(), holdMargin: 0.5 + random(), lastAuctionAllIn: int(2),
      minTargetLength: 2 + int(9), firstPriceShade: 0.5 + random(),
      marketWeight: random(), marketWindow: 1 + int(20), behindBoost: random(), oppBalanceCap: int(2),
    };
  const v: MatchView = {
    lexicon: lex, rack, unseen, unseenTotal: totalOf(unseen), auctionsLeft,
    letter: String.fromCharCode(65 + slot), balance: int(401), score: int(301),
    firstPrice: int(2) === 1,
    opponents: Array.from({ length: int(6) }, () => ({ balance: int(401), score: int(301) })),
    history: Array.from({ length: int(30) }, () => ({ slot: int(26), paid: int(31), mine: int(2) === 1 })),
  };
  samples.push({ v, p, odds: acquireOdds(v, p) });
}
// Include adversarial large racks from the strategy regression test, at the
// largest deficit and full acquisition odds, as well as zero odds and no extra.
for (const letters of ["BCDFGHJKLMNPQRSTVWXZ", "AEIOUAEIOUAEIOURSTLN", "EEEEAAAIIIOORRSSTTNL"]) {
  for (const winRate of [0, 0.7, 1]) {
    const rack = new Uint8Array(26);
    const unseen = new Uint8Array(BAG_COUNTS);
    for (const c of letters) { const s = c.charCodeAt(0) - 65; rack[s]!++; unseen[s]!--; }
    for (const extra of [-1, 4, 16, 18]) {
      const v = { ...samples[0]!.v, rack, unseen, unseenTotal: totalOf(unseen), auctionsLeft: 67,
        letter: String.fromCharCode(65 + Math.max(0, extra)), balance: 100 };
      const p = { ...PLANNER_PARAMS, maxDeficit: 3, winRate };
      samples.push({ v, p, odds: acquireOdds(v, p) });
    }
  }
}
const times = { oldPotential: [] as number[], newPotential: [] as number[],
  oldDecision: [] as number[], newDecision: [] as number[],
  oldBid: [] as number[], newBid: [] as number[], oldPlay: [] as number[], newPlay: [] as number[] };
function timed<T>(out: number[], f: () => T): T {
  const start = performance.now(); const result = f(); out.push(performance.now() - start); return result;
}
// Warm both implementations before timing. No result caches are used.
for (const { v, p, odds } of samples.slice(0, 50)) {
  potentials(lex, v.rack, 4, odds, p); fastPotentials(lex, v.rack, 4, odds, p);
  planner(p).play(v); fastPlanner(p).play(v);
}
for (let k = 0; k < samples.length; k++) {
  const { v, p, odds } = samples[k]!;
  const extra = k % 5 === 0 ? -1 : v.letter.charCodeAt(0) - 65;
  let oldPotential: [number, number], newPotential: [number, number];
  let oldDecision: unknown, newDecision: unknown;
  const old = planner(p), fast = fastPlanner(p);
  // Alternate measurement order to avoid consistently favoring either side.
  const measureOld = () => {
    oldPotential = timed(times.oldPotential, () => potentials(lex, v.rack, extra, odds, p));
    oldDecision = timed(times.oldDecision, () => [timed(times.oldBid, () => old.bid(v)), timed(times.oldPlay, () => old.play(v))]);
  };
  const measureNew = () => {
    newPotential = timed(times.newPotential, () => fastPotentials(lex, v.rack, extra, odds, p));
    newDecision = timed(times.newDecision, () => [timed(times.newBid, () => fast.bid(v)), timed(times.newPlay, () => fast.play(v))]);
  };
  if (k % 2) { measureOld(); measureNew(); } else { measureNew(); measureOld(); }
  assert.deepStrictEqual(newPotential!, oldPotential!, `potentials case ${k}`);
  assert.deepStrictEqual(newDecision!, oldDecision!, `bid/play case ${k}`);
  if (times.newDecision.at(-1)! > 30) console.log(`Slow new decision case ${k}: ${times.newDecision.at(-1)!.toFixed(3)} ms, rack ${Array.from(v.rack, (n, s) => String.fromCharCode(65 + s).repeat(n)).join("")}, maxDeficit ${p.maxDeficit}`);
  if ((k + 1) % 500 === 0) console.log(`Checked ${k + 1} cases`);
}
function stats(values: number[]): string {
  const sorted = [...values].sort((a, b) => a - b);
  return `mean ${(values.reduce((a, b) => a + b, 0) / values.length).toFixed(3)} ms, ` +
    `p99 ${sorted[Math.ceil(sorted.length * 0.99) - 1]!.toFixed(3)} ms, max ${sorted.at(-1)!.toFixed(3)} ms`;
}
console.log(`Exact equivalence passed: ${samples.length} cases, ${lex.words.length} words (seed 0x9e3779b9).`);
for (const [name, values] of Object.entries(times)) console.log(`${name}: ${stats(values)}`);
