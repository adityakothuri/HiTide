// Reference strategies: the repo's starter bot and the strategy report's
// "long-word hoarding" hybrid. Kept for benchmarking.

import { LETTER_VALUE, totalOf } from "../lexicon.js";
import type { MatchView, Policy } from "../policy.js";

/** bot-starter's original strategy, unchanged in behaviour. */
export const starter: Policy = {
  name: "Starter",
  bid(v) {
    const value = LETTER_VALUE[v.letter] ?? 1;
    const have = v.rack[v.letter.charCodeAt(0) - 65]!;
    const want = have === 0 ? value + 2 : Math.max(1, value);
    return Math.min(want, Math.max(0, v.balance));
  },
  play(v) {
    const i = v.lexicon.first(v.rack, 2);
    return i < 0 ? null : v.lexicon.words[i]!;
  },
};

export interface ReportParams {
  baseMultiplier: number;
  vowelPremium: number;
  commonPremium: number;
  duplicatePenalty: number;
  targetVowelRatio: number;
  balanceCorrection: number;
  qWithoutUPenalty: number;
  lowBalanceThreshold: number;
  lowBalanceScale: number;
  maxBid: number;
  primaryMinLength: number;
  pressureRackSize: number;
  emergencyMinLength: number;
}

export const REPORT_PARAMS: ReportParams = {
  baseMultiplier: 1.7095,
  vowelPremium: 1.5702,
  commonPremium: 0.5009,
  duplicatePenalty: 1.2931,
  targetVowelRatio: 0.4434,
  balanceCorrection: 3.8199,
  qWithoutUPenalty: 4.6577,
  lowBalanceThreshold: 30, // not given in the report
  lowBalanceScale: 0.7429,
  maxBid: 18,
  primaryMinLength: 7,
  pressureRackSize: 10,
  emergencyMinLength: 5,
};

const VOWEL_SLOTS = [0, 4, 8, 14, 20]; // A E I O U
const isVowel = (s: number) => VOWEL_SLOTS.includes(s);
const COMMON = new Set(["R", "S", "T", "L", "N"]);

export function vowelCount(rack: Uint8Array): number {
  let n = 0;
  for (const s of VOWEL_SLOTS) n += rack[s]!;
  return n;
}

/** The strategy report's letter valuation (before balance limits). */
export function reportWorth(v: MatchView, p: ReportParams): number {
  const slot = v.letter.charCodeAt(0) - 65;
  const vowel = isVowel(slot);
  let worth = p.baseMultiplier * (LETTER_VALUE[v.letter] ?? 1);
  if (vowel) worth += p.vowelPremium;
  if (COMMON.has(v.letter)) worth += p.commonPremium;
  const tiles = totalOf(v.rack);
  const ratio = tiles > 0 ? vowelCount(v.rack) / tiles : p.targetVowelRatio;
  const gap = p.targetVowelRatio - ratio;
  worth += p.balanceCorrection * (vowel ? gap : -gap);
  worth -= p.duplicatePenalty * v.rack[slot]!;
  if (v.letter === "Q" && v.rack[20] === 0) worth -= p.qWithoutUPenalty;
  return worth;
}

export function reportHybrid(p: ReportParams = REPORT_PARAMS, name = "Report"): Policy {
  return {
    name,
    bid(v) {
      let worth = reportWorth(v, p);
      if (v.balance < p.lowBalanceThreshold) worth *= p.lowBalanceScale;
      const bid = Math.min(Math.round(worth), p.maxBid, Math.floor(v.balance));
      return Math.max(0, bid);
    },
    play(v) {
      let i = v.lexicon.best(v.rack, p.primaryMinLength);
      if (i < 0 && totalOf(v.rack) >= p.pressureRackSize) {
        i = v.lexicon.best(v.rack, p.emergencyMinLength);
      }
      return i < 0 ? null : v.lexicon.words[i]!;
    },
  };
}
