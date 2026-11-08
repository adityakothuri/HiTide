// Fast word index shared by the live bot and the offline simulator.
//
// Each word is stored as a 26-letter count vector plus a bitmask of the
// letters it uses, so most words are rejected with one mask test.

import * as fs from "node:fs";

export const LETTER_VALUE: Record<string, number> = {
  A: 1, B: 3, C: 3, D: 2, E: 1, F: 4, G: 2, H: 4, I: 1, J: 8,
  K: 5, L: 1, M: 3, N: 1, O: 1, P: 3, Q: 10, R: 1, S: 1, T: 1,
  U: 1, V: 4, W: 4, X: 8, Y: 4, Z: 10,
};

export const SLOT_VALUE: number[] = Array.from(
  { length: 26 },
  (_, i) => LETTER_VALUE[String.fromCharCode(65 + i)] ?? 0,
);

/** Standard Scrabble distribution without blanks, 98 tiles, by slot A..Z. */
export const BAG_COUNTS: number[] = [
  9, 2, 2, 4, 12, 2, 3, 2, 9, 1, 1, 4, 2, 6, 8, 2, 1, 6, 4, 6, 4, 2, 2, 1, 2, 1,
];

export const slotOf = (c: string): number => c.charCodeAt(0) - 65;
export const letterOf = (slot: number): string => String.fromCharCode(65 + slot);

/** Server reward: face values times the length multiplier (integer math). */
export function rewardFor(base: number, length: number): number {
  if (length <= 3) return base;
  if (length === 4) return Math.floor((base * 3) / 2);
  if (length === 5) return base * 2;
  if (length === 6) return Math.floor((base * 5) / 2);
  return base * 3;
}

export function wordReward(word: string): number {
  let base = 0;
  for (const c of word) base += LETTER_VALUE[c] ?? 0;
  return rewardFor(base, word.length);
}

/** A rack as 26 counts. Cheap to copy and compare. */
export type Counts = Uint8Array;

export function countsFromMap(rack: Map<string, number>): Counts {
  const out = new Uint8Array(26);
  for (const [c, n] of rack) {
    const s = slotOf(c);
    if (s >= 0 && s < 26 && n > 0) out[s] = Math.min(255, out[s]! + n);
  }
  return out;
}

export function countsFromString(letters: string): Counts {
  const out = new Uint8Array(26);
  for (const c of letters) out[slotOf(c)]!++;
  return out;
}

export function totalOf(counts: Counts): number {
  let n = 0;
  for (let s = 0; s < 26; s++) n += counts[s]!;
  return n;
}

export function maskOf(counts: Counts): number {
  let m = 0;
  for (let s = 0; s < 26; s++) if (counts[s]! > 0) m |= 1 << s;
  return m;
}

export class Lexicon {
  readonly words: string[];
  readonly length: Uint8Array;
  readonly mask: Int32Array;
  readonly counts: Uint8Array; // words.length * 26
  readonly reward: Int32Array;
  /** Nonzero count slots, in A..Z order, for each word. */
  readonly slotOffsets: Uint32Array;
  readonly slots: Uint8Array;
  /** firstOfLength[L] = index of the first word with length <= L. */
  private readonly firstOfLength: Int32Array;

  /** `words` uppercase A-Z; stored longest first, then alphabetical. */
  constructor(words: string[]) {
    this.words = [...new Set(words)]
      .filter((w) => w.length >= 2 && /^[A-Z]+$/.test(w))
      .sort((a, b) => b.length - a.length || (a < b ? -1 : a > b ? 1 : 0));
    const n = this.words.length;
    this.length = new Uint8Array(n);
    this.mask = new Int32Array(n);
    this.counts = new Uint8Array(n * 26);
    this.reward = new Int32Array(n);
    this.slotOffsets = new Uint32Array(n + 1);
    const slots: number[] = [];
    let maxLen = 0;
    for (let i = 0; i < n; i++) {
      const w = this.words[i]!;
      let base = 0;
      let m = 0;
      for (let j = 0; j < w.length; j++) {
        const s = w.charCodeAt(j) - 65;
        this.counts[i * 26 + s]!++;
        m |= 1 << s;
        base += SLOT_VALUE[s]!;
      }
      this.slotOffsets[i] = slots.length;
      for (let s = 0; s < 26; s++) if (m & (1 << s)) slots.push(s);
      this.length[i] = w.length;
      this.mask[i] = m;
      this.reward[i] = rewardFor(base, w.length);
      maxLen = Math.max(maxLen, w.length);
    }
    this.slotOffsets[n] = slots.length;
    this.slots = new Uint8Array(slots);
    this.firstOfLength = new Int32Array(maxLen + 2).fill(n);
    for (let i = n - 1; i >= 0; i--) {
      for (let L = this.length[i]!; L <= maxLen + 1; L++) {
        if (this.firstOfLength[L]! > i) this.firstOfLength[L] = i;
        else break;
      }
    }
  }

  static fromFile(path: string | URL): Lexicon {
    const words = fs
      .readFileSync(path, "utf8")
      .split("\n")
      .map((l) => l.trim().toUpperCase());
    return new Lexicon(words);
  }

  /** Index of the first word no longer than `maxLen`. */
  startAt(maxLen: number): number {
    if (maxLen >= this.firstOfLength.length) return 0;
    return maxLen < 0 ? this.words.length : this.firstOfLength[maxLen]!;
  }

  spells(i: number, have: Counts): boolean {
    const base = i * 26;
    for (let s = 0; s < 26; s++) {
      if (this.counts[base + s]! > have[s]!) return false;
    }
    return true;
  }

  /** Highest-reward word of at least `minLen` letters; ties go to the
   *  earlier (longer, then alphabetical) word. -1 if none. */
  best(have: Counts, minLen: number, maxLen = 99): number {
    const tiles = totalOf(have);
    if (tiles < minLen) return -1;
    const rackMask = maskOf(have);
    let best = -1;
    let bestReward = -1;
    for (let i = this.startAt(Math.min(tiles, maxLen)); i < this.words.length; i++) {
      if (this.length[i]! < minLen) break;
      if ((this.mask[i]! & ~rackMask) !== 0) continue;
      if (this.reward[i]! > bestReward && this.spells(i, have)) {
        best = i;
        bestReward = this.reward[i]!;
      }
    }
    return best;
  }

  /** First spellable word (longest, then alphabetical) of >= minLen. */
  first(have: Counts, minLen: number): number {
    const tiles = totalOf(have);
    if (tiles < minLen) return -1;
    const rackMask = maskOf(have);
    for (let i = this.startAt(tiles); i < this.words.length; i++) {
      if (this.length[i]! < minLen) break;
      if ((this.mask[i]! & ~rackMask) !== 0) continue;
      if (this.spells(i, have)) return i;
    }
    return -1;
  }

  /** Up to `k` spellable words of >= minLen, highest reward first (ties:
   *  dictionary order). */
  topSpellable(have: Counts, minLen: number, k: number): number[] {
    const tiles = totalOf(have);
    if (tiles < minLen || k <= 0) return [];
    const rackMask = maskOf(have);
    const found: number[] = [];
    for (let i = this.startAt(tiles); i < this.words.length; i++) {
      if (this.length[i]! < minLen) break;
      if ((this.mask[i]! & ~rackMask) !== 0) continue;
      if (this.spells(i, have)) found.push(i);
    }
    found.sort((a, b) => this.reward[b]! - this.reward[a]! || a - b);
    return found.slice(0, k);
  }

  has(word: string): boolean {
    return this.index.has(word);
  }

  private _index: Set<string> | null = null;
  private get index(): Set<string> {
    this._index ??= new Set(this.words);
    return this._index;
  }
}

/** Remove `word`'s letters from `have`, returning a new rack. */
export function minusWord(have: Counts, word: string): Counts {
  const out = new Uint8Array(have);
  for (const c of word) out[slotOf(c)]!--;
  return out;
}
