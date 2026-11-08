// Clone v2: a behavioral model of one public bot, fitted by bench/live/clone-engine.mts.
// Bids come from a censored-normal regression on the bot's own state (rack,
// cash, rounds left, auction mechanism, rival budgets); words from a fitted
// play style. Only public match history is used to fit it.
import type { MatchView, Policy } from './policy.js';
import { lexforgeFeatures } from './strategies/lexforgeFeatures.js';
import { chooseImitationWord, type ImitationStyle } from './fleetPolicy.js';

export const CLONE_FEATURE_SET = 'clone-v2';
export const CLONE_NAME_PATTERN = /^Pegasus-v[A-Za-z0-9-]{1,40}$/;

export interface CloneValidation {
  trainMatches: number; testMatches: number; testBids: number; testWords: number;
  bidMAE: number | null; baselineBidMAE: number | null;
  outcomeAgreement: number | null; baselineOutcomeAgreement: number | null;
  wordAgreement: number | null; playTimingAccuracy: number | null;
}
export interface CloneModel {
  schemaVersion: 2; kind: 'clone';
  source: { botId: number; name: string; rank: number; rating: number; snapshotAt: string; matchIds: number[]; latestMatchEndedAt: string | null };
  style: ImitationStyle;
  bid: { features: typeof CLONE_FEATURE_SET; means: number[]; scales: number[]; weights: number[]; sigma: number };
  validation: CloneValidation;
  evidence: { usableMatches: number; skippedMatches: number; rackSamples: number; trainingRows: number };
  fittedAt: string; fitSeconds: number;
}

type FeatureView = Pick<MatchView, 'letter' | 'rack' | 'balance' | 'auctionsLeft' | 'unseen' | 'unseenTotal' | 'lexicon' | 'firstPrice' | 'opponents'>;

/** LexForge's 42 rack/cash features plus mechanism, phase and rival-budget terms. */
export function cloneFeatures(v: FeatureView, style: ImitationStyle): number[] {
  const base = lexforgeFeatures(v, style);
  const fp = v.firstPrice ? 1 : 0;
  const rival = Math.max(0, ...v.opponents.map(o => o.balance));
  const face = base[32]!; // face_value of the auctioned letter
  return [...base, fp, rival, fp * Math.min(v.balance, rival + 1), v.auctionsLeft, fp * v.auctionsLeft, fp * face];
}

/** Deterministic per-state noise (approx. standard normal) so a clone's bid spread matches its source. */
export function stateNoise(v: Pick<MatchView, 'letter' | 'auctionsLeft' | 'balance' | 'rack'>): number {
  const key = `${v.letter}|${v.auctionsLeft}|${v.balance}|${Array.from(v.rack).join(',')}`;
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619);
  let sum = 0;
  for (let i = 0; i < 4; i++) {
    h = Math.imul(h ^ (h >>> 15), 2246822519); h = Math.imul(h ^ (h >>> 13), 3266489917);
    sum += ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }
  return (sum - 2) * Math.sqrt(3);
}

export function predictCloneBid(model: Pick<CloneModel, 'bid' | 'style'>, v: FeatureView): number {
  const x = cloneFeatures(v, model.style);
  if (x.length !== model.bid.means.length) throw Error('Clone model feature mismatch');
  let mu = model.bid.weights[0]!;
  for (let i = 0; i < x.length; i++) mu += model.bid.weights[i + 1]! * (x[i]! - model.bid.means[i]!) / model.bid.scales[i]!;
  return mu;
}

export function validateCloneModel(m: CloneModel): void {
  if (m?.schemaVersion !== 2 || m.kind !== 'clone' || m.bid?.features !== CLONE_FEATURE_SET) throw Error('Not a clone-v2 model');
  const n = m.bid.means.length;
  const finite = (xs: number[]) => xs.every(Number.isFinite);
  if (m.bid.weights.length !== n + 1 || m.bid.scales.length !== n || !finite(m.bid.weights) || !finite(m.bid.means) || m.bid.scales.some(s => !Number.isFinite(s) || s <= 0)) throw Error('Invalid clone coefficients');
  if (!Number.isFinite(m.bid.sigma) || m.bid.sigma <= 0 || m.bid.sigma > 40) throw Error('Invalid clone sigma');
  if (m.style.primaryLength < 2 || m.style.recoveryMinLength < 2 || m.style.liquidateAt < 0) throw Error('Invalid clone word style');
}

export function clonePolicy(model: CloneModel, name = `Clone(${model.source.name})`): Policy {
  validateCloneModel(model);
  return {
    name,
    bid(v) {
      const balance = Math.floor(v.balance);
      if (balance <= 0) return 0;
      const rivalCap = Math.max(0, ...v.opponents.map(p => p.balance)) + 1;
      // Final auction: the remaining cash is worthless afterwards, as every source bot plays it.
      if (v.auctionsLeft === 0) return v.firstPrice ? Math.min(balance, rivalCap) : balance;
      let amount = predictCloneBid(model, v) + model.bid.sigma * stateNoise(v);
      if (v.firstPrice) amount = Math.min(amount, rivalCap);
      return Math.max(0, Math.min(balance, Math.round(amount)));
    },
    play: v => chooseImitationWord(v, model.style),
  };
}
