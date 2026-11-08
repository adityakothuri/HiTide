/**
 * LexForge Hyper-Optimized: rack-aware ScrabbleBot policy (pasted candidate, under test).
 * Exports renamed to lexforgeOpt / LEXFORGE_OPT_PARAMS so it sits beside lexforge.ts.
 */
import { maskOf, totalOf, type Lexicon } from '../lexicon.js';
import type { MatchView, Policy } from '../policy.js';
import { lexforgeFeatures } from './lexforgeFeatures.js';
import { LEXFORGE_TREES } from './lexforgeTrees.js';
import { LEXFORGE_MODEL } from './lexforgeModel.js';

interface BidTree {
  value: number;
  feature?: number;
  cut?: number;
  left?: BidTree;
  right?: BidTree;
}

export const LEXFORGE_OPT_PARAMS = {
  noise: 0,
  useTrees: 0,
  primaryMinLength: 7,
  primaryMinScore: 45,
  primaryTileCost: 3,
  cashBalance: 16,
  recoveryMinLength: 5,
  liquidateAt: 0,
  desperateBalance: 5,
  desperateMinLength: 2,
  paceBalance: 16,
  paceShare: 0.60,
  bidScale: 1.60,
  bidShift: 0,
  modelBlend: 0.15,
  baseTileBid: 2.4,
  faceBidWeight: 0.75,
  deltaBidWeight: 0.92,
  futureWinShare: 0.28,
  futureMissingLimit: 4,
  forecastPenaltyPerTile: 0.72,
  candidateLimit: 240,
  searchStates: 4000,
  endgameStart: 10,
  lowCashPlay: 18,
  holdMargin: 0.08,
  firstPriceShade: 0.73,
};

type Params = typeof LEXFORGE_OPT_PARAMS;
type Rack = Uint8Array;

const BAG = new Uint8Array([
  9, 2, 2, 4, 12, 2, 3, 2, 9, 1, 1, 4, 2,
  6, 8, 2, 1, 6, 4, 6, 4, 2, 2, 1, 2, 1,
]);
const FACE = new Uint8Array([
  1, 3, 3, 2, 1, 4, 2, 4, 1, 8, 5, 1, 3,
  1, 1, 3, 10, 1, 1, 1, 1, 4, 4, 8, 4, 10,
]);
const VOWEL_MASK = (1 << 0) | (1 << 4) | (1 << 8) | (1 << 14) | (1 << 20);

const ZOBRIST = new BigUint64Array(26 * 16);
{
  let seed = 0x9e3779b97f4a7c15n;
  for (let i = 0; i < ZOBRIST.length; i++) {
    seed ^= seed >> 30n;
    seed = (seed * 0xbf58476d1ce4e5b9n) & 0xffffffffffffffffn;
    seed ^= seed >> 27n;
    seed = (seed * 0x94d049bb133111ebn) & 0xffffffffffffffffn;
    seed ^= seed >> 31n;
    ZOBRIST[i] = seed;
  }
}

function hashRack(rack: Rack): bigint {
  let h = 0n;
  for (let i = 0; i < 26; i++) {
    const c = rack[i]!;
    if (c > 0) h ^= ZOBRIST[(i << 4) + (c < 15 ? c : 15)]!;
  }
  return h;
}

interface Candidate {
  index: number;
  length: number;
  reward: number;
  mask: number;
  counts: Uint8Array;
}

interface Plan {
  score: number;
  first: number;
}

interface Evaluation {
  plan: Plan;
  estimate: number;
}

interface LexiconIndex {
  uniqueIndices: Int32Array;
  uniqueLengths: Uint8Array;
  uniqueRewards: Int16Array;
  uniqueMasks: Int32Array;
  uniqueCounts: Uint8Array;
  startByLen: Int32Array;
  longWordCutoff: number;
  maxRewardPerTileByLen: Float32Array;
  liquidationCache: Map<bigint, Plan>;
  evaluationCache: Map<bigint, Evaluation>;
}

const lexiconIndexCache = new WeakMap<Lexicon, LexiconIndex>();

function getLexiconIndex(lex: Lexicon): LexiconIndex {
  let idx = lexiconIndexCache.get(lex);
  if (idx) return idx;

  const nWords = lex.words.length;
  const seenHashes = new Set<bigint>();
  const tempIndices: number[] = [];
  const tempCounts: Uint8Array[] = [];
  const scratch = new Uint8Array(26);

  for (let i = 0; i < nWords; i++) {
    const len = lex.length[i]!;
    if (len < 2) break;
    const w = lex.words[i]!;
    scratch.fill(0);
    let valid = true;
    for (let j = 0; j < len; j++) {
      const c = w.charCodeAt(j);
      const k = (c >= 97 ? c - 32 : c) - 65;
      if (k < 0 || k >= 26) {
        valid = false;
        break;
      }
      scratch[k]!++;
    }
    if (!valid) continue;

    const h = hashRack(scratch);
    if (!seenHashes.has(h)) {
      seenHashes.add(h);
      tempIndices.push(i);
      tempCounts.push(Uint8Array.from(scratch));
    }
  }

  const numUnique = tempIndices.length;
  const uniqueIndices = new Int32Array(numUnique);
  const uniqueLengths = new Uint8Array(numUnique);
  const uniqueRewards = new Int16Array(numUnique);
  const uniqueMasks = new Int32Array(numUnique);
  const uniqueCounts = new Uint8Array(numUnique * 26);

  const maxLen = numUnique > 0 ? lex.length[tempIndices[0]!]! : 15;
  const startByLen = new Int32Array(maxLen + 2).fill(numUnique);
  const maxRewardPerTileByLen = new Float32Array(maxLen + 2);

  let longWordCutoff = numUnique;
  for (let u = 0; u < numUnique; u++) {
    const wordIdx = tempIndices[u]!;
    const len = lex.length[wordIdx]!;
    const rew = lex.reward[wordIdx]!;
    uniqueIndices[u] = wordIdx;
    uniqueLengths[u] = len;
    uniqueRewards[u] = rew;
    uniqueMasks[u] = lex.mask[wordIdx]!;
    uniqueCounts.set(tempCounts[u]!, u * 26);

    if (len < 7 && longWordCutoff === numUnique) {
      longWordCutoff = u;
    }
    for (let l = len; l <= maxLen + 1; l++) {
      if (startByLen[l]! === numUnique) startByLen[l] = u;
      const rpt = rew / len;
      if (rpt > maxRewardPerTileByLen[l]!) maxRewardPerTileByLen[l] = rpt;
    }
  }

  idx = {
    uniqueIndices,
    uniqueLengths,
    uniqueRewards,
    uniqueMasks,
    uniqueCounts,
    startByLen,
    longWordCutoff,
    maxRewardPerTileByLen,
    liquidationCache: new Map(),
    evaluationCache: new Map(),
  };
  lexiconIndexCache.set(lex, idx);
  return idx;
}

function clamp(x: number, low: number, high: number): number {
  return x < low ? low : x > high ? high : x;
}

function letterIndex(letter: string): number {
  if (!letter) return -1;
  const c = letter.charCodeAt(0);
  const uppercase = c >= 97 && c <= 122 ? c - 32 : c;
  return uppercase >= 65 && uppercase <= 90 ? uppercase - 65 : -1;
}

function popcount32(m: number): number {
  m = m - ((m >>> 1) & 0x55555555);
  m = (m & 0x33333333) + ((m >>> 2) & 0x33333333);
  return (((m + (m >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24;
}

function playableCandidates(idx: LexiconIndex, rack: Rack, p: Params): Candidate[] {
  const availableMask = maskOf(rack);
  const n = totalOf(rack);
  if (n < 2) return [];

  const maxStart = idx.startByLen.length - 1;
  const startU = idx.startByLen[n < maxStart ? n : maxStart]!;
  const numUnique = idx.uniqueIndices.length;
  const masks = idx.uniqueMasks;
  const counts = idx.uniqueCounts;
  const lengths = idx.uniqueLengths;
  const rewards = idx.uniqueRewards;
  const indices = idx.uniqueIndices;

  const matched: Candidate[] = [];

  outer: for (let u = startU; u < numUnique; u++) {
    if ((masks[u]! & ~availableMask) !== 0) continue;
    const base = u * 26;
    for (let j = 0; j < 26; j++) {
      if (counts[base + j]! > rack[j]!) continue outer;
    }
    matched.push({
      index: indices[u]!,
      length: lengths[u]!,
      reward: rewards[u]!,
      mask: masks[u]!,
      counts: counts.subarray(base, base + 26),
    });
  }

  matched.sort((a, b) => b.reward - a.reward || b.length - a.length || a.index - b.index);
  if (matched.length <= p.candidateLimit) return matched;

  const chosen: Candidate[] = [];
  const picked = new Uint8Array(matched.length);
  const byLength = new Uint16Array(32);
  const lengthQuota = Math.max(5, Math.floor(p.candidateLimit / 14));

  for (let i = 0; i < matched.length; i++) {
    const w = matched[i]!;
    if (byLength[w.length]! < lengthQuota) {
      chosen.push(w);
      picked[i] = 1;
      byLength[w.length]!++;
    }
  }
  for (let i = 0; i < matched.length && chosen.length < p.candidateLimit; i++) {
    if (!picked[i]) chosen.push(matched[i]!);
  }
  chosen.sort((a, b) => b.reward - a.reward || b.length - a.length);
  return chosen;
}

function liquidate(lex: Lexicon, idx: LexiconIndex, rack: Rack, p: Params): Plan {
  const nTotal = totalOf(rack);
  if (nTotal < 2) return { score: 0, first: -1 };

  const rHash = hashRack(rack);
  const rootKey = rHash ^ BigInt(p.candidateLimit << 16 | p.searchStates);
  if (idx.liquidationCache.size > 6000) idx.liquidationCache.clear();
  const hit = idx.liquidationCache.get(rootKey);
  if (hit) return hit;

  const candidates = playableCandidates(idx, rack, p);
  if (candidates.length === 0) {
    const emptyPlan = { score: 0, first: -1 };
    idx.liquidationCache.set(rootKey, emptyPlan);
    return emptyPlan;
  }

  const memo = new Map<bigint, Plan>();
  const stateLimit = nTotal > 14 ? Math.min(1800, p.searchStates) : p.searchStates;
  let states = 0;

  const working = Uint8Array.from(rack);
  const numCandidates = candidates.length;

  function solve(tilesLeft: number, currentHash: bigint, startIdx: number): Plan {
    if (tilesLeft < 2) return { score: 0, first: -1 };
    const saved = memo.get(currentHash);
    if (saved) return saved;
    if (++states > stateLimit) return { score: 0, first: -1 };

    let bestScore = 0;
    let bestFirst = -1;
    let available = 0;
    for (let j = 0; j < 26; j++) {
      if (working[j]! > 0) available |= 1 << j;
    }

    for (let cIdx = startIdx; cIdx < numCandidates; cIdx++) {
      const word = candidates[cIdx]!;
      const wLen = word.length;
      if (wLen > tilesLeft) continue;
      if ((word.mask & ~available) !== 0) continue;

      const wCounts = word.counts;
      let fits = true;
      for (let j = 0; j < 26; j++) {
        if (wCounts[j]! > working[j]!) {
          fits = false;
          break;
        }
      }
      if (!fits) continue;

      const remTiles = tilesLeft - wLen;
      let nextHash = currentHash;
      for (let j = 0; j < 26; j++) {
        const wc = wCounts[j]!;
        if (wc > 0) {
          const oldC = working[j]!;
          const newC = oldC - wc;
          working[j] = newC;
          nextHash ^= ZOBRIST[(j << 4) + (oldC < 15 ? oldC : 15)]!;
          if (newC > 0) nextHash ^= ZOBRIST[(j << 4) + (newC < 15 ? newC : 15)]!;
        }
      }

      const sub = remTiles >= 2 ? solve(remTiles, nextHash, 0) : { score: 0, first: -1 };

      for (let j = 0; j < 26; j++) {
        working[j]! += wCounts[j]!;
      }

      const totalScore = word.reward + sub.score;
      if (
        totalScore > bestScore ||
        (totalScore === bestScore && bestFirst >= 0 && wLen > lex.length[bestFirst]!)
      ) {
        bestScore = totalScore;
        bestFirst = word.index;
      }
    }

    const answer = { score: bestScore, first: bestFirst };
    memo.set(currentHash, answer);
    return answer;
  }

  const result = solve(nTotal, rHash, 0);
  idx.liquidationCache.set(rootKey, result);
  return result;
}

function poissonTail(lambda: number, n: number): number {
  if (n <= 0) return 1;
  if (lambda <= 0) return 0;
  const e = Math.exp(-lambda);
  if (n === 1) return 1 - e;
  if (n === 2) return 1 - e * (1 + lambda);
  if (n === 3) return 1 - e * (1 + lambda + 0.5 * lambda * lambda);
  if (n === 4) return 1 - e * (1 + lambda + 0.5 * lambda * lambda + (lambda * lambda * lambda) / 6);
  let term = e;
  let cdf = term;
  for (let k = 1; k < n; k++) {
    term *= lambda / k;
    cdf += term;
  }
  return clamp(1 - cdf, 0, 1);
}

function computeUnseenBag(rack: Rack, v?: MatchView): { unseen: Uint8Array; totalUnseen: number } {
  const unseen = Uint8Array.from(BAG);
  let totalUnseen = 0;
  for (let j = 0; j < 26; j++) {
    const rem = Math.max(0, unseen[j]! - rack[j]!);
    unseen[j] = rem;
  }
  if (v && v.opponents) {
    for (let o = 0; o < v.opponents.length; o++) {
      const oppRack = (v.opponents[o] as { rack?: ArrayLike<number> }).rack;
      if (oppRack && oppRack.length === 26) {
        for (let j = 0; j < 26; j++) {
          unseen[j] = Math.max(0, unseen[j]! - (oppRack[j] ?? 0));
        }
      }
    }
  }
  for (let j = 0; j < 26; j++) totalUnseen += unseen[j]!;
  return { unseen, totalUnseen: Math.max(1, totalUnseen) };
}

function estimateRack(
  idx: LexiconIndex,
  rack: Rack,
  unseen: Uint8Array,
  totalUnseen: number,
  remaining: number,
  guaranteed: number,
  p: Params,
): number {
  if (remaining <= 0) return guaranteed;
  const n = totalOf(rack);
  const maxMissing = Math.min(p.futureMissingLimit, remaining);
  const maxLen = n + maxMissing;
  if (maxLen < 7) return guaranteed;

  const rackMask = maskOf(rack);
  const maxStart = idx.startByLen.length - 1;
  const startU = idx.startByLen[maxLen < maxStart ? maxLen : maxStart]!;
  const endU = idx.longWordCutoff;

  const masks = idx.uniqueMasks;
  const rewards = idx.uniqueRewards;
  const counts = idx.uniqueCounts;

  let biggestBonus = 0;
  const scaleFactor = (remaining / totalUnseen) * p.futureWinShare;

  for (let u = startU; u < endU; u++) {
    const reward = rewards[u]!;
    if (reward - guaranteed - p.forecastPenaltyPerTile <= biggestBonus) continue;

    const absent = masks[u]! & ~rackMask;
    if (popcount32(absent) > maxMissing) continue;

    const base = u * 26;
    let deficits = 0;
    let probability = 1;

    for (let j = 0; j < 26; j++) {
      const wCount = counts[base + j]!;
      if (wCount === 0) continue;
      const need = wCount - rack[j]!;
      if (need > 0) {
        deficits += need;
        if (deficits > maxMissing) break;
        const avail = unseen[j]!;
        if (need > avail) {
          probability = 0;
          break;
        }
        const lambda = avail * scaleFactor;
        probability *= poissonTail(lambda, need);
        if (probability < 0.0002) {
          probability = 0;
          break;
        }
      }
    }

    if (deficits === 0 || deficits > maxMissing || probability <= 0) continue;

    const bonus =
      probability * Math.max(0, reward - guaranteed) - p.forecastPenaltyPerTile * deficits;
    if (bonus > biggestBonus) biggestBonus = bonus;
  }

  return guaranteed + biggestBonus;
}

function evaluate(
  lex: Lexicon,
  idx: LexiconIndex,
  rack: Rack,
  unseen: Uint8Array,
  totalUnseen: number,
  remaining: number,
  p: Params,
): Evaluation {
  const rHash = hashRack(rack);
  const key = rHash ^ (BigInt(remaining) << 48n) ^ (BigInt(totalUnseen) << 56n);
  if (idx.evaluationCache.size > 6000) idx.evaluationCache.clear();
  const hit = idx.evaluationCache.get(key);
  if (hit) return hit;

  const plan = liquidate(lex, idx, rack, p);
  const estimate = estimateRack(idx, rack, unseen, totalUnseen, remaining, plan.score, p);
  const result = { plan, estimate };
  idx.evaluationCache.set(key, result);
  return result;
}

function stateNoise(v: MatchView): number {
  let h = 2166136261 ^ v.auctionsLeft ^ (Math.floor(v.balance) << 8);
  if (v.letter) h = Math.imul(h ^ v.letter.charCodeAt(0), 16777619);
  for (let i = 0; i < 26; i++) {
    h = Math.imul(h ^ (v.rack[i] ?? 0), 16777619);
  }
  let sum = 0;
  for (let i = 0; i < 4; i++) {
    h = Math.imul(h ^ (h >>> 15), 2246822519);
    h = Math.imul(h ^ (h >>> 13), 3266489917);
    sum += ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }
  return (sum - 2) * 1.7320508075688772;
}

function reconstructedBid(v: MatchView, p: Params): { mean: number; sigma: number } {
  if (p.modelBlend <= 0) return { mean: 0, sigma: 0 };
  const features = lexforgeFeatures(v);
  let mean = LEXFORGE_MODEL.weights[0]!;
  for (let i = 0; i < features.length; i++) {
    mean +=
      (LEXFORGE_MODEL.weights[i + 1]! * (features[i]! - LEXFORGE_MODEL.means[i]!)) /
      LEXFORGE_MODEL.scales[i]!;
  }
  let sigma = LEXFORGE_MODEL.sigma;
  if (p.useTrees) {
    mean = LEXFORGE_TREES.initial;
    for (const root of LEXFORGE_TREES.trees) {
      let node: BidTree = root;
      while (node.feature !== undefined)
        node = features[node.feature]! <= node.cut! ? node.left! : node.right!;
      mean += LEXFORGE_TREES.rate * node.value;
    }
    sigma = LEXFORGE_TREES.sigma;
  }
  return {
    mean: Number.isFinite(mean) ? Math.max(0, mean) : 0,
    sigma: Number.isFinite(sigma) ? sigma : 0,
  };
}

function priorTileValue(index: number, rack: Rack, unseen: Uint8Array, p: Params): number {
  const duplicates = rack[index]!;
  let usefulness = duplicates === 0 ? 1 : duplicates === 1 ? 0.78 : 0.46;
  if (duplicates >= 3) usefulness = 0.25;

  if (index === 16 && rack[20]! === 0) {
    usefulness *= unseen[20]! === 0 ? 0.05 : 0.23;
  }
  if (index === 20 && rack[16]! > 0 && rack[20]! === 0) {
    usefulness *= 1.85;
  }
  if (index === 9) usefulness *= 0.75;

  const vowels = rack[0]! + rack[4]! + rack[8]! + rack[14]! + rack[20]!;
  const total = totalOf(rack);
  const isVowel = ((1 << index) & VOWEL_MASK) !== 0;
  if (total >= 3) {
    if (isVowel && vowels / total < 0.28) usefulness *= 1.24;
    else if (!isVowel && vowels / total > 0.62) usefulness *= 1.15;
    if (isVowel && vowels / total > 0.60) usefulness *= 0.76;
  }
  if (index === 18 || index === 4 || index === 17 || index === 19 || index === 13) {
    usefulness *= 1.06;
  }
  return (p.baseTileBid + p.faceBidWeight * FACE[index]!) * usefulness;
}

export function lexforgeOpt(
  overrides: Partial<Params> = {},
  name = 'LexForgeOptimized',
): Policy {
  const p: Params = { ...LEXFORGE_OPT_PARAMS, ...overrides };
  return {
    name,
    bid(v) {
      const balance = Math.floor(v.balance);
      if (balance <= 0) return 0;
      const k = letterIndex(String(v.letter));
      if (k < 0) return 0;

      const idx = getLexiconIndex(v.lexicon);
      const remaining = Math.max(0, v.auctionsLeft);
      const rack = Uint8Array.from(v.rack);
      const { unseen, totalUnseen } = computeUnseenBag(rack, v);

      const augmented = Uint8Array.from(rack);
      augmented[k] = augmented[k]! + 1;
      const unseenAfter = Uint8Array.from(unseen);
      if (unseenAfter[k]! > 0) unseenAfter[k]!--;

      const before = evaluate(v.lexicon, idx, rack, unseen, totalUnseen, remaining, p);
      const after = evaluate(
        v.lexicon,
        idx,
        augmented,
        unseenAfter,
        Math.max(1, totalUnseen - 1),
        remaining,
        p,
      );

      const immediateGain = Math.max(0, after.plan.score - before.plan.score);
      const expectedGain = Math.max(0, after.estimate - before.estimate);
      const maxRival = Math.max(0, ...v.opponents.map(o => Math.floor(o.balance)));

      if (remaining === 0) {
        if (immediateGain <= 0) return 0;
        return v.firstPrice ? Math.min(balance, maxRival + 1) : balance;
      }

      const prior = priorTileValue(k, rack, unseen, p);
      let intrinsic = Math.max(
        prior,
        prior * 0.55 + p.deltaBidWeight * Math.max(expectedGain, immediateGain),
      );

      if (after.plan.first >= 0 && v.lexicon.length[after.plan.first]! >= 7 && immediateGain >= 35) {
        intrinsic = Math.max(intrinsic, immediateGain * 0.95);
      }

      if (p.modelBlend > 0) {
        const modeled = reconstructedBid(v, p);
        intrinsic = intrinsic * (1 - p.modelBlend) + Math.max(0, modeled.mean) * p.modelBlend;
        if (p.noise !== 0) intrinsic += p.noise * modeled.sigma * stateNoise(v);
      }

      const futureBuyingBudget = 8 + remaining * 0.80;
      const liquidity = clamp(0.77 + (0.25 * balance) / futureBuyingBudget, 0.62, 1.36);
      let amount = intrinsic * liquidity;

      if (remaining <= p.endgameStart) {
        const urgency = (p.endgameStart - remaining) / Math.max(1, p.endgameStart);
        if (immediateGain > 0) {
          amount = Math.max(amount, immediateGain * (1 + 0.8 * urgency));
        } else {
          amount *= Math.max(0.18, 1 - 0.70 * urgency);
        }
      }

      amount = amount * p.bidScale + p.bidShift;
      if (v.firstPrice) amount *= p.firstPriceShade;
      if (balance < p.paceBalance && remaining > p.endgameStart) {
        amount = Math.min(amount, Math.floor(balance * p.paceShare));
      }

      let finalBid = clamp(Math.round(amount), 0, balance);
      if (v.firstPrice && finalBid > maxRival + 1) {
        finalBid = Math.min(balance, maxRival + 1);
      }
      return finalBid;
    },

    play(v) {
      const idx = getLexiconIndex(v.lexicon);
      const rack = Uint8Array.from(v.rack);
      const remaining = Math.max(0, v.auctionsLeft);
      const { unseen, totalUnseen } = computeUnseenBag(rack, v);

      const outcome = evaluate(v.lexicon, idx, rack, unseen, totalUnseen, remaining, p);
      const first = outcome.plan.first;
      if (first < 0) return null;
      if (remaining <= p.liquidateAt) return v.lexicon.words[first]!;

      const length = v.lexicon.length[first]!;
      const reward = v.lexicon.reward[first]!;
      const rackSize = totalOf(rack);
      const balance = Math.floor(v.balance);

      if (length >= p.primaryMinLength) return v.lexicon.words[first]!;

      const residualRack = Uint8Array.from(rack);
      const wordStr = v.lexicon.words[first]!;
      for (let j = 0; j < wordStr.length; j++) {
        const k = letterIndex(wordStr[j]!);
        if (k >= 0 && residualRack[k]! > 0) residualRack[k]!--;
      }
      const residualEval = evaluate(v.lexicon, idx, residualRack, unseen, totalUnseen, remaining, p);
      const playNowEV = reward + residualEval.estimate;
      const upgradeGain = outcome.estimate - playNowEV;

      if (balance <= p.lowCashPlay && length >= p.recoveryMinLength && upgradeGain <= reward * 0.25) {
        return v.lexicon.words[first]!;
      }

      if (rackSize >= 15 && length >= 5 && upgradeGain <= reward * 0.20) {
        return v.lexicon.words[first]!;
      }

      if (
        remaining <= p.endgameStart &&
        (outcome.estimate <= outcome.plan.score * (1 + p.holdMargin) || upgradeGain <= 2.5)
      ) {
        return v.lexicon.words[first]!;
      }

      if (
        length >= 6 &&
        reward >= 28 &&
        balance < p.cashBalance * 2 &&
        upgradeGain <= reward * p.holdMargin
      ) {
        return v.lexicon.words[first]!;
      }

      if (balance <= p.desperateBalance && length >= p.desperateMinLength) {
        return v.lexicon.words[first]!;
      }

      return null;
    },
  };
}
