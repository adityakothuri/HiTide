// Simulated copies of strong bots on the live server, fitted from public
// match data (bench/live/profile.mts over 400 recent matches): each bids
// a*face + b + c*vowel plus noise, and hoards for long words like the
// original does. Used as tougher, realistic opponents in the simulator.

import { LETTER_VALUE, totalOf } from "../lexicon.js";
import type { Policy } from "../policy.js";
import { planner } from "./planner.js";

export interface MimicParams {
  a: number;     // bid per face point
  b: number;     // flat bid
  c: number;     // extra for vowels
  sd: number;    // bid noise
  shrink: number; // scales a and b: observed bids are winners' (biased high)
  primaryMinLength: number; // hoard until a word this long is playable
  pressureRackSize: number; // ...or the rack holds this many tiles
  emergencyMinLength: number;
  /** 1: play words like the tuned planner (hold-or-play + final cash-in). */
  smartPlay?: number;
  /** >0: scale bids by balance per remaining auction / budgetTau (clamped 0.3..1.2). */
  budgetTau?: number;
}

/** Fitted from live data (top bid on tiles won), by bot. */
export const LIVE_BOTS: Record<string, Omit<MimicParams, "shrink">> = {
  LUCENT: { a: 2.78, b: 9.16, c: 0.55, sd: 7.5, primaryMinLength: 7, pressureRackSize: 12, emergencyMinLength: 5 },
  Bron: { a: 2.29, b: 8.58, c: 0.68, sd: 6.64, primaryMinLength: 7, pressureRackSize: 12, emergencyMinLength: 5 },
  GodOfThudner: { a: 2.59, b: 12.03, c: -0.78, sd: 6.42, primaryMinLength: 6, pressureRackSize: 10, emergencyMinLength: 4 },
  Maverick: { a: 3.01, b: 9.91, c: 0.17, sd: 8.89, primaryMinLength: 7, pressureRackSize: 11, emergencyMinLength: 5 },
  StickBot: { a: 2.39, b: 12.2, c: 0.77, sd: 6.4, primaryMinLength: 6, pressureRackSize: 10, emergencyMinLength: 4 },
  Tow57: { a: 2.03, b: 11.28, c: -0.48, sd: 5.71, primaryMinLength: 7, pressureRackSize: 10, emergencyMinLength: 4 },
  SoapConsumers: { a: 2.31, b: 11.35, c: 0.16, sd: 5.78, primaryMinLength: 6, pressureRackSize: 9, emergencyMinLength: 4 },
  Odysseus: { a: 2.47, b: 12.32, c: -0.67, sd: 5.6, primaryMinLength: 7, pressureRackSize: 11, emergencyMinLength: 5 },
};

/** Deterministic noise from the decision state, so runs are reproducible. */
function noise(key: string): number {
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619);
  // two uniforms -> approximately normal (Irwin-Hall with 4 terms)
  let sum = 0;
  for (let k = 0; k < 4; k++) {
    h = Math.imul(h ^ (h >>> 15), 2246822519);
    h = Math.imul(h ^ (h >>> 13), 3266489917);
    sum += ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }
  return (sum - 2) * Math.sqrt(3); // mean 0, sd 1
}

// Play logic of the round-1 tuned planner (P1), used by smartPlay mimics.
const smart = planner({
  maxDeficit: 3, winRate: 0.729, pointsToBid: 1.981, faceFloor: 2.622, flatFloor: 4.89,
  spendTarget: 6.325, spendMin: 0.823, spendMax: 1.237, maxBidShare: 0.762, holdMargin: 1.111, minTargetLength: 6,
});

export function mimic(p: MimicParams, name: string): Policy {
  return {
    name,
    bid(v) {
      const face = LETTER_VALUE[v.letter] ?? 1;
      const vowel = "AEIOU".includes(v.letter) ? 1 : 0;
      const key = `${name}|${v.auctionsLeft}|${v.letter}|${v.balance}|${v.score}|${v.history.length}`;
      let raw = p.shrink * (p.a * face + p.b) + p.c * vowel + p.sd * noise(key);
      if (p.budgetTau && p.budgetTau > 0) {
        const perAuction = v.balance / (v.auctionsLeft + 1);
        raw *= Math.min(1.2, Math.max(0.3, perAuction / p.budgetTau));
      }
      return Math.max(0, Math.min(Math.floor(v.balance), Math.round(raw)));
    },
    play(v) {
      if (p.smartPlay) return smart.play(v);
      const lex = v.lexicon;
      let i = lex.best(v.rack, p.primaryMinLength);
      if (i < 0 && totalOf(v.rack) >= p.pressureRackSize) i = lex.best(v.rack, p.emergencyMinLength);
      return i < 0 ? null : lex.words[i]!;
    },
  };
}
