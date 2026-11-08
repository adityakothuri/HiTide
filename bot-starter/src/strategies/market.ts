// Strategy D: market-anchored bidding with planner play.
//
// Live data (bench/live/market.mts) shows prices are set by the whole
// table's budget, and the strongest bots win by buying many vowels and
// common consonants at the going rate. So each bid starts from the live
// median winning bid for that letter, scaled by `anchor`, then moves with
// how much the letter helps this rack (planner marginal potential), rack
// balance (vowels) and duplicates. Words are played with the planner.

import { LETTER_VALUE, totalOf } from "../lexicon.js";
import type { MatchView, Policy } from "../policy.js";
import { type PlannerParams, PLANNER_PARAMS, planner, potentials } from "./planner.js";

/** Median winning bid per letter A..Z on the live server (400 matches). */
export const LIVE_WINNING_BID = [
  13, 18, 20, 16, 13, 21, 14, 24, 12, 31, 27, 13, 19, 13, 12, 18, 29, 13, 15, 12, 12, 20, 21, 33.5, 23, 39,
];

export interface MarketParams {
  anchor: number;        // multiple of the live winning bid to start from
  anchor1pt: number;     // extra multiple for 1-point consonants (L N R S T)
  anchorMid: number;     // extra multiple for 2-5 point letters
  anchorHigh: number;    // extra multiple for 8-10 point letters
  pointsToBid: number;   // currency per point of marginal potential
  vowelTarget: number;   // desired vowel share of the rack
  vowelPush: number;     // +-share of bid for vowels when the rack is off target
  duplicatePenalty: number; // bid share removed per copy already held
  maxBidShare: number;   // cap as share of balance (before the last auction)
  reserveRounds: number; // keep enough balance for this many anchor-priced bids
  paceK: number;         // >0: cap each bid at balance * min(1, paceK / (auctionsLeft + 1))
  paceFaceBoost: number; // pacing cap grows by this much per face point above 1
  brokeBalance: number;  // below this balance, cash in a word to refill...
  brokeMinLength: number; // ...if one at least this long is playable
  plan: Partial<PlannerParams>; // planner settings for valuation and play
}

export const MARKET_PARAMS: MarketParams = {
  anchor: 1.0,
  anchor1pt: 1,
  anchorMid: 1,
  anchorHigh: 1,
  pointsToBid: 1.0,
  vowelTarget: 0.4,
  vowelPush: 0.3,
  duplicatePenalty: 0.15,
  maxBidShare: 0.6,
  reserveRounds: 0,
  paceK: 0,
  paceFaceBoost: 0,
  brokeBalance: 0,
  brokeMinLength: 5,
  plan: {
    maxDeficit: 1, winRate: 0.733, pointsToBid: 1.222, faceFloor: 2.414, flatFloor: 4.374,
    spendTarget: 5.606, spendMin: 1.338, spendMax: 3.241, maxBidShare: 0.987, holdMargin: 1.059,
    minTargetLength: 5,
  },
};

/** Market defaults plus the improved word choice (E10). */
export const SEARCH_PLAN = { playSearch: 25 };

const VOWEL = new Set([0, 4, 8, 14, 20]);

function oddsFor(v: MatchView, p: PlannerParams): Float64Array {
  const odds = new Float64Array(26);
  const share = v.unseenTotal > 0 ? Math.min(1, v.auctionsLeft / v.unseenTotal) : 0;
  for (let s = 0; s < 26; s++) odds[s] = p.winRate * (1 - (1 - share) ** v.unseen[s]!);
  return odds;
}

export function market(o: Partial<MarketParams> = {}, name = "Market"): Policy {
  const p: MarketParams = { ...MARKET_PARAMS, ...o, plan: { ...MARKET_PARAMS.plan, ...o.plan } };
  const plan: PlannerParams = { ...PLANNER_PARAMS, ...p.plan };
  const player = planner(plan, `${name}-play`);
  return {
    name,
    bid(v) {
      const balance = Math.floor(v.balance);
      if (balance <= 0) return 0;
      if (v.auctionsLeft === 0) {
        if (!v.firstPrice) return balance; // money is worthless after this
        const richest = Math.max(0, ...v.opponents.map((q) => q.balance));
        return Math.min(balance, richest + 1);
      }
      const slot = v.letter.charCodeAt(0) - 65;
      const [now, withLetter] = potentials(v.lexicon, v.rack, slot, oddsFor(v, plan), plan);
      const marginal = Math.max(0, withLetter - now);

      const face = LETTER_VALUE[v.letter] ?? 1;
      const group = VOWEL.has(slot) ? 1 : face === 1 ? p.anchor1pt : face <= 5 ? p.anchorMid : p.anchorHigh;
      let worth = p.anchor * group * LIVE_WINNING_BID[slot]! + p.pointsToBid * marginal;
      const tiles = totalOf(v.rack);
      if (VOWEL.has(slot) && tiles > 0) {
        let vowels = 0;
        for (const s of VOWEL) vowels += v.rack[s]!;
        const gap = p.vowelTarget - vowels / tiles; // + means short of vowels
        worth *= 1 + p.vowelPush * Math.max(-1, Math.min(1, gap * 4));
      }
      worth *= Math.max(0, 1 - p.duplicatePenalty * v.rack[slot]!);

      let cap = Math.floor(balance * p.maxBidShare);
      if (p.reserveRounds > 0) {
        // Leave room for later purchases unless the end is near.
        const reserve = Math.min(v.auctionsLeft, p.reserveRounds) * p.anchor * 12;
        cap = Math.min(cap, Math.max(0, balance - reserve) + Math.floor(worth * 0.5));
      }
      if (p.paceK > 0) {
        // Spread the budget over the match: early bids can't drain it.
        // High-value letters (worth 3x face in a 7-letter word) may spend more.
        const k = p.paceK * (1 + p.paceFaceBoost * (face - 1));
        cap = Math.min(cap, Math.floor(balance * Math.min(1, k / (v.auctionsLeft + 1))));
      }
      if (v.firstPrice) worth *= 0.8;
      return Math.max(0, Math.min(balance, Math.max(1, cap), Math.round(worth)));
    },
    play(v) {
      const word = player.play(v);
      if (word || v.balance >= p.brokeBalance) return word;
      // Out of money: refill by cashing in a decent word now.
      const i = v.lexicon.best(v.rack, p.brokeMinLength, plan.maxWordLength);
      return i < 0 ? null : v.lexicon.words[i]!;
    },
  };
}

export { LETTER_VALUE };
