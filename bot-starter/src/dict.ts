// Portfolio queries reuse the existing ENABLE index; no second wordlist or SDK.
import { type Counts, type Lexicon, maskOf, totalOf, minusWord } from './lexicon.js';

export function evaluateLeave(rack: Counts): number {
  const n = totalOf(rack);
  if (!n) return 0;
  let vowels = 0, utility = 0, duplicates = 0;
  for (let s = 0; s < 26; s++) {
    const c = String.fromCharCode(65 + s), k = rack[s]!;
    if ('AEIOU'.includes(c)) vowels += k;
    utility += k * ('SERTAINL'.includes(c) ? 0.8 : 'XZJK'.includes(c) ? 0.5 : 0);
    duplicates += Math.max(0, k - 1) ** 2;
  }
  const q = rack[16]! ? (rack[20]! || rack[8]! ? 2 : -6) : 0;
  return utility - 1.4 * duplicates - 2.2 * Math.abs(vowels - n * 0.4) + q;
}

interface Analysis { leaves: Map<number, number>; best: Map<number, { index: number; objective: number }>; playable: number[]; completion: Float64Array; bingo: Uint8Array }
const caches = new WeakMap<Lexicon, Map<string, Analysis>>();
function analyze(lex: Lexicon, rack: Counts): Analysis {
  let cache = caches.get(lex);
  if (!cache) caches.set(lex, cache = new Map());
  const key = Array.from(rack).join(',');
  const hit = cache.get(key);
  if (hit) return hit;
  const out: Analysis = { leaves: new Map(), best: new Map(), playable: [], completion: new Float64Array(26), bingo: new Uint8Array(26) };
  const mask = maskOf(rack), n = totalOf(rack);
  for (let i = lex.startAt(n + 1); i < lex.words.length; i++) {
    const absent = lex.mask[i]! & ~mask;
    if (absent && (absent & (absent - 1))) continue;
    const len = lex.length[i]!;
    if (absent && len < 6) continue;
    let missing = 0, slot = -1;
    for (let j = lex.slotOffsets[i]!; j < lex.slotOffsets[i + 1]!; j++) {
      const s = lex.slots[j]!, deficit = lex.counts[i * 26 + s]! - rack[s]!;
      if (deficit > 0) { missing += deficit; slot = s; if (missing > 1) break; }
    }
    if (!missing) out.playable.push(i);
    else if (missing === 1 && len >= 6) {
      // Best completion per letter, not a sum over mutually exclusive anagrams.
      out.completion[slot] = Math.max(out.completion[slot]!, lex.reward[i]!);
      if (len >= 7) out.bingo[slot] = 1;
    }
  }
  out.playable.sort((a, b) => lex.reward[b]! - lex.reward[a]! || lex.length[b]! - lex.length[a]! || a - b);
  if (cache.size >= 12000) cache.clear();
  cache.set(key, out);
  return out;
}

export function findPlayableWords(lex: Lexicon, rack: Counts): number[] {
  return analyze(lex, rack).playable.slice();
}

export function evaluateRackPortfolio(lex: Lexicon, rack: Counts, remaining: ArrayLike<number>, lambda = 0.65) {
  const a = analyze(lex, rack);
  let choice = a.best.get(lambda);
  if (!choice) {
    const leaves = candidateLeaves(lex, rack);
    let index = -1, objective = lambda * evaluateLeave(rack);
    for (const i of a.playable) {
      const value = lex.reward[i]! + lambda * leaves.get(i)!;
      if (index < 0 || value > objective) { objective = value; index = i; }
    }
    choice = { index, objective }; a.best.set(lambda, choice);
  }
  const best = choice.index, objective = choice.objective;
  let nearBingoEV = 0, bingoAvailable = false, total = 0;
  for (let s = 0; s < 26; s++) total += remaining[s]!;
  for (let s = 0; s < 26; s++) {
    const probability = total > 0 ? remaining[s]! / total : 0;
    nearBingoEV += probability * a.completion[s]!;
    if (probability && a.bingo[s]) bingoAvailable = true;
  }
  return {
    bestImmediateWord: best < 0 ? null : lex.words[best]!,
    bestImmediateScore: a.playable.length ? lex.reward[a.playable[0]!]! : 0,
    bestObjective: objective,
    nearBingoEV, bingoAvailable,
  };
}

export function candidateLeaves(lex: Lexicon, rack: Counts): Map<number, number> {
  const a = analyze(lex, rack);
  if (a.leaves.size !== a.playable.length) {
    for (const i of a.playable) a.leaves.set(i, evaluateLeave(minusWord(rack, lex.words[i]!)));
  }
  return a.leaves;
}
