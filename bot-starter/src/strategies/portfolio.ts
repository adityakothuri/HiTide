import { candidateLeaves, evaluateLeave, evaluateRackPortfolio, findPlayableWords } from '../dict.js';
import { slotOf, SLOT_VALUE, totalOf } from '../lexicon.js';
import type { MatchView, Policy } from '../policy.js';

export const PARAMS = {
  lambda: 0.65, immediate: 0.9, stem: 0.35, leave: 0.7,
  faceFloor: 1.5, flatFloor: 1, vickrey: 0.9, firstPrice: 0.63,
  maxSpendRatio: 0.28, cashSpendRatio: 0.8, reserve: 12,
  blockPremium: 3, blockBalance: 30,
};
export type PortfolioParams = typeof PARAMS;
// One development probe. Keep the prompt-like starting configuration available.
export const TUNED_PARAMS: PortfolioParams = {
  ...PARAMS, faceFloor: 4, flatFloor: 4, immediate: 1.8, stem: 0.8,
  maxSpendRatio: 0.45, reserve: 8, vickrey: 0.95, firstPrice: 0.68,
};
const remaining = (v: MatchView): ArrayLike<number> => v.remainingBagEstimate ?? v.unseen;

function eligible(v: MatchView, i: number, bingoAvailable: boolean, n: number, leave: number, leaves: Map<number, number>): boolean {
  const len = v.lexicon.length[i]!, score = v.lexicon.reward[i]!;
  if (v.auctionsLeft <= 4) return true;
  if (v.auctionsLeft <= 8 && (len >= 4 || score >= 8)) return true;
  if (v.auctionsLeft <= 12 && (len >= 5 || score >= 14)) return true;
  if (len >= 7) return true;
  if (len === 6 && (score >= 24 || n >= 8 || !bingoAvailable)) return true;
  if (v.balance < 16 && (score >= 10 || len >= 4)) return true;
  if (v.balance < 28 && (len >= 5 || score >= 16)) return true;
  if (n >= 9 && leave < 0 && (len >= 5 || (len === 4 && leaves.get(i)! > leave))) return true;
  return false;
}

export function chooseWord(v: MatchView, p = PARAMS): string | null {
  const info = evaluateRackPortfolio(v.lexicon, v.rack, remaining(v), p.lambda);
  let word: string | null = null, objective = -Infinity;
  const n = totalOf(v.rack), leave = evaluateLeave(v.rack), leaves = candidateLeaves(v.lexicon, v.rack);
  // Filter cash-in eligibility BEFORE maximizing: an ineligible best word
  // must not conceal a playable recovery or endgame word.
  for (const i of findPlayableWords(v.lexicon, v.rack)) {
    if (!eligible(v, i, info.bingoAvailable, n, leave, leaves)) continue;
    const w = v.lexicon.words[i]!;
    const value = v.lexicon.reward[i]! + p.lambda * leaves.get(i)!;
    if (value > objective) { objective = value; word = w; }
  }
  return word;
}

export function decideBid(v: MatchView, p = PARAMS): number {
  // No client can play a tile awarded in the transaction ending the match.
  if (!v.balance || v.auctionsLeft === 0) return 0;
  const slot = slotOf(v.letter), bag = remaining(v);
  const before = evaluateRackPortfolio(v.lexicon, v.rack, bag, p.lambda);
  const rack = new Uint8Array(v.rack); rack[slot]!++;
  const after = evaluateRackPortfolio(v.lexicon, rack, bag, p.lambda);
  const delta = Math.max(0, after.bestObjective - before.bestObjective);
  const stem = Math.max(0, after.nearBingoEV - before.nearBingoEV);
  if (totalOf(v.rack) >= 9 && after.bestImmediateScore <= before.bestImmediateScore && stem <= 0)
    return v.balance > p.reserve ? 1 : 0;
  const cashIn = after.bestImmediateScore > before.bestImmediateScore && chooseWord({ ...v, rack }, p) !== null;
  let worth = Math.max(p.faceFloor * SLOT_VALUE[slot]! + p.flatFloor,
    p.immediate * delta + p.stem * stem + p.leave * (evaluateLeave(rack) - evaluateLeave(v.rack)));
  if (cashIn) worth = Math.max(worth, 0.95 * delta);
  if (!v.firstPrice && p.blockPremium > 0) {
    for (const opponent of v.opponents) {
      if (!opponent.knownRack || opponent.balance < p.blockBalance) continue;
      const denied = new Uint8Array(opponent.knownRack); denied[slot]!++;
      if (v.lexicon.best(opponent.knownRack, 7) < 0 && v.lexicon.best(denied, 7) >= 0) {
        worth += Math.min(p.blockPremium, worth * 0.25); break;
      }
    }
  }
  const cap = Math.min(v.balance * (cashIn ? p.cashSpendRatio : p.maxSpendRatio),
    cashIn ? v.balance : Math.max(0, v.balance - p.reserve));
  const affordable = v.firstPrice ? Math.max(0, ...v.opponents.map(o => o.balance)) + 1 : Infinity;
  return Math.max(0, Math.floor(Math.min(v.balance, cap, affordable, worth * (v.firstPrice ? p.firstPrice : p.vickrey))));
}

export function portfolio(overrides: Partial<PortfolioParams> = {}, name = 'Portfolio'): Policy {
  const p = { ...PARAMS, ...overrides };
  return { name, bid: v => decideBid(v, p), play: v => chooseWord(v, p) };
}
