// Clone engine v2: fit a behavioral model of one public bot from its completed matches.
//
//   node --import tsx bench/live/clone-engine.mts --bot <botId> --out <model.json>
//
// 1. Replays each source match from the bot's seat. Starting racks are private, so
//    each match is replayed with several racks sampled consistently with the public
//    word/auction history (data augmentation over the unknown).
// 2. Fits the word-play style (length target, reward floor, recovery, liquidation).
// 3. Fits a censored-normal bid regression on the bot's own state: wins give exact
//    bids, losses give upper bounds, cash-capped wins give lower bounds. Sigma is
//    learned jointly, so the clone reproduces the source's bid spread.
// 4. Validates on the latest 30% of matches against the old median-per-letter copy,
//    then refits on all matches for the deployed model.
import { readFileSync, writeFileSync, renameSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Lexicon, maskOf, totalOf, BAG_COUNTS, wordReward } from '../../src/lexicon.js';
import { sampleStartingRacks, type ArchivedMatch } from '../../src/replay.js';
import { chooseImitationWord, type ImitationStyle } from '../../src/fleetPolicy.js';
import { cloneFeatures, predictCloneBid, validateCloneModel, CLONE_FEATURE_SET, type CloneModel, type CloneValidation } from '../../src/clonePolicy.js';
import { LIVE_WINNING_BID } from '../../src/strategies/market.js';
import type { MatchView } from '../../src/policy.js';

const RACK_SAMPLES = 3;
const TEST_SHARE = 0.3;
const MIN_MATCHES = 8;
const EPOCHS = 1400;

type Raw = Record<string, any>;
interface BidRow { match: number; sample: number; rack: Uint8Array; balance: number; score: number; left: number; letter: string; unseen: Uint8Array; won: boolean; top: number; paid: number; firstPrice: boolean; rivals: number[]; x?: number[]; best?: number[] }
interface WordRow { match: number; sample: number; rack: Uint8Array; balance: number; left: number; reward: number; word: string; best?: number[] }

const lexicon = Lexicon.fromFile(fileURLToPath(new URL('../../../spacetimedb/wordlist.txt', import.meta.url)));

function decode(raw: Raw): ArchivedMatch {
  const tops = new Map(raw.tops.map((t: Raw) => [Number(t.auction_id), Number(t.top_bid)]));
  const count = raw.participants.length, derived = (98 - raw.auctions.length) / count;
  const starting = Number.isInteger(derived) && derived >= 0 ? derived : Number(raw.state.starting_rack_size);
  const m: ArchivedMatch = {
    id: Number(raw.state.id), createdAt: Number(raw.state.created_at[0]), startingRack: starting,
    bots: raw.participants.map((p: Raw) => Number(p.bot_id)),
    auctions: raw.auctions.map((a: Raw) => ({ id: Number(a.auction_id), letter: String(a.letter), winner: a.winner_bot_id[0] === 0 ? Number(a.winner_bot_id[1]) : null, paid: Number(a.paid), top: Number(tops.get(Number(a.auction_id))), time: Number(a.closed_at[0]) })).sort((a: any, b: any) => a.id - b.id),
    plays: raw.plays.map((p: Raw) => ({ bot: Number(p.bot_id), word: String(p.word), reward: Number(p.total_reward), time: Number(p.played_at[0]) })),
  };
  if (m.auctions.some(a => !Number.isFinite(a.top))) throw Error('Missing archived bid');
  return m;
}

/** Replay one match from the hero's seat with one sampled starting rack. */
function replaySeat(raw: Raw, hero: number, sample: number, bids: BidRow[], words: WordRow[]) {
  const m = decode(raw), firstPrice = raw.state.auction_type[0] !== 1;
  const rack = sampleStartingRacks(m, m.id * 7919 + sample).get(hero);
  if (!rack) throw Error('Hero not seated');
  const initial = new Uint8Array(rack), drawn = new Uint8Array(26);
  const own = m.plays.filter(p => p.bot === hero).sort((a, b) => a.time - b.time);
  const rivals = new Map(m.bots.filter(b => b !== hero).map(b => [b, 100]));
  const rivalEvents = [
    ...m.auctions.filter(a => a.winner !== null && a.winner !== hero).map(a => ({ time: a.time, bot: a.winner!, delta: -a.paid })),
    ...m.plays.filter(p => p.bot !== hero).map(p => ({ time: p.time, bot: p.bot, delta: p.reward })),
  ].sort((a, b) => a.time - b.time);
  let balance = 100, score = 0, ownIndex = 0, rivalIndex = 0;
  const localBids: BidRow[] = [], localWords: WordRow[] = [];
  for (let round = 0; round < m.auctions.length; round++) {
    const a = m.auctions[round]!, opened = round ? m.auctions[round - 1]!.time : m.createdAt;
    while (rivalIndex < rivalEvents.length && rivalEvents[rivalIndex]!.time <= opened) {
      const e = rivalEvents[rivalIndex++]!; rivals.set(e.bot, rivals.get(e.bot)! + e.delta);
    }
    while (ownIndex < own.length && own[ownIndex]!.time <= a.time) {
      const p = own[ownIndex++]!;
      localWords.push({ match: m.id, sample, rack: new Uint8Array(rack), balance, left: m.auctions.length - round - 1, reward: p.reward, word: p.word });
      for (const c of p.word) { const s = c.charCodeAt(0) - 65; if (!rack[s]) throw Error('Impossible word consumption'); rack[s]!--; }
      balance += p.reward; score += p.reward;
    }
    drawn[a.letter.charCodeAt(0) - 65]!++;
    const unseen = Uint8Array.from(BAG_COUNTS, (n, s) => Math.max(0, n - drawn[s]! - initial[s]!));
    localBids.push({ match: m.id, sample, rack: new Uint8Array(rack), balance, score, left: m.auctions.length - round - 1, letter: a.letter, unseen, won: a.winner === hero, top: a.top, paid: a.paid, firstPrice, rivals: [...rivals.values()] });
    if (a.winner === hero) { rack[a.letter.charCodeAt(0) - 65]!++; balance -= a.paid; }
  }
  const me = raw.participants.find((p: Raw) => Number(p.bot_id) === hero);
  if (balance !== Number(me.balance) || score !== Number(me.score)) throw Error('Final account mismatch');
  bids.push(...localBids); words.push(...localWords);
}

function observe(matchIds: number[], cache: Record<string, Raw>, hero: number) {
  const bids: BidRow[] = [], words: WordRow[] = [], skipped: { match: number; reason: string }[] = [];
  for (const id of [...matchIds].sort((a, b) => a - b)) {
    const raw = cache[id];
    if (!raw) { skipped.push({ match: id, reason: 'not cached' }); continue; }
    try {
      const b: BidRow[] = [], w: WordRow[] = [];
      for (let k = 0; k < RACK_SAMPLES; k++) replaySeat(raw, hero, k, b, w);
      bids.push(...b); words.push(...w);
    } catch (e) { skipped.push({ match: id, reason: String(e instanceof Error ? e.message : e) }); }
  }
  return { bids, words, skipped };
}

const scoreCache = new Map<string, number[]>();
function bestByLength(rack: Uint8Array): number[] {
  const key = rack.join(',');
  const hit = scoreCache.get(key); if (hit) return hit;
  const values = Array(10).fill(0), mask = maskOf(rack);
  for (let i = lexicon.startAt(totalOf(rack)); i < lexicon.words.length; i++) {
    if ((lexicon.mask[i]! & ~mask) !== 0 || !lexicon.spells(i, rack)) continue;
    for (let len = 2; len <= Math.min(9, lexicon.length[i]!); len++) values[len] = Math.max(values[len]!, lexicon.reward[i]!);
  }
  if (scoreCache.size > 30000) scoreCache.clear();
  scoreCache.set(key, values); return values;
}

function asView(r: { rack: Uint8Array; balance: number; left: number; letter?: string; score?: number; unseen?: Uint8Array; firstPrice?: boolean; rivals?: number[] }): MatchView {
  return { letter: r.letter ?? 'E', rack: r.rack, balance: r.balance, score: r.score ?? 0, auctionsLeft: r.left, unseen: r.unseen ?? new Uint8Array(BAG_COUNTS), unseenTotal: r.unseen ? totalOf(r.unseen) : 98, opponents: (r.rivals ?? []).map(balance => ({ balance, score: 0 })), firstPrice: r.firstPrice ?? false, history: [], lexicon };
}

const playsNow = (s: ImitationStyle, r: { left: number; balance: number; best: number[] }) =>
  r.left <= s.liquidateAt ? r.best[2]! > 0 : (r.best[s.primaryLength]! >= s.primaryMinReward && r.best[s.primaryLength]! > 0) || (r.balance < s.recoveryBalance && r.best[s.recoveryMinLength]! > 0);

/** Grid-search when the bot cashes in (balanced error), then which word it picks. */
function fitStyle(bids: BidRow[], words: WordRow[]): ImitationStyle {
  const negatives = bids.map(r => ({ ...r, best: r.best ??= bestByLength(r.rack) }));
  const positives = words.map(r => ({ ...r, best: r.best ??= bestByLength(r.rack) }));
  let chosen: ImitationStyle = { primaryLength: 7, primaryMinReward: 0, recoveryBalance: 15, recoveryMinLength: 5, liquidateAt: 0, primaryTileCost: 0 }, best = Infinity;
  for (const primaryLength of [7, 6, 8, 5, 4]) for (const primaryMinReward of [0, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70]) for (const recoveryBalance of [0, 5, 10, 15, 20, 30, 40, 50]) for (const recoveryMinLength of [5, 4, 6, 3, 2]) for (const liquidateAt of [0, 1, 2, 3]) {
    if (recoveryMinLength > primaryLength) continue;
    const s = { primaryLength, primaryMinReward, recoveryBalance, recoveryMinLength, liquidateAt, primaryTileCost: 0 };
    let misses = 0, falsePlays = 0;
    for (const r of positives) if (!playsNow(s, r)) misses++;
    for (const r of negatives) if (playsNow(s, r)) falsePlays++;
    const error = misses / Math.max(1, positives.length) + falsePlays / Math.max(1, negatives.length);
    if (error < best) { best = error; chosen = s; }
  }
  let hits = -1;
  for (const primaryTileCost of [0, 1, 2, 3, 4]) {
    const s = { ...chosen, primaryTileCost };
    let hit = 0;
    for (const r of words) { const w = chooseImitationWord(asView(r), s); if (w && wordReward(w) === r.reward) hit++; }
    if (hit > hits) { hits = hit; chosen = s; }
  }
  return chosen;
}

function cdf(z: number) {
  const x = Math.abs(z), t = 1 / (1 + .2316419 * x), phi = .3989422804014327 * Math.exp(-x * x / 2);
  const p = 1 - phi * t * (.319381530 + t * (-.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  return Math.max(1e-12, Math.min(1 - 1e-12, z >= 0 ? p : 1 - p));
}

/** Censored-normal negative log likelihood with gradients w.r.t. mu and log sigma. */
function censoredLoss(r: BidRow, mu: number, s: number): [number, number, number] {
  if (r.won && r.top < r.balance) { const e = (mu - r.top) / s; return [.5 * e * e + Math.log(s), e / s, 1 - e * e]; }
  if (!r.won && r.top >= r.balance) return [0, 0, 0]; // could not have won anyway: uninformative
  const c = r.won ? r.balance - .5 : r.top + .5, z = (c - mu) / s, phi = .3989422804014327 * Math.exp(-z * z / 2);
  if (r.won) { const p = 1 - cdf(z); return [-Math.log(p), -phi / (s * p), -z * phi / p]; }
  const p = cdf(z); return [-Math.log(p), phi / (s * p), z * phi / p];
}

function fitBid(rows: BidRow[], style: ImitationStyle) {
  const train = rows.filter(r => r.left > 0 && r.balance > 0);
  for (const r of train) r.x = cloneFeatures(asView(r), style);
  const n = train[0]!.x!.length;
  const means = Array.from({ length: n }, (_, j) => train.reduce((s, r) => s + r.x![j]!, 0) / train.length);
  const scales = means.map((m, j) => Math.max(.01, Math.sqrt(train.reduce((s, r) => s + (r.x![j]! - m) ** 2, 0) / train.length)));
  const z = train.map(r => [1, ...r.x!.map((x, j) => (x - means[j]!) / scales[j]!)]);
  const w = Array(n + 2).fill(0); w[0] = 12; w[n + 1] = Math.log(5); // last slot: log sigma
  const m1 = Array(n + 2).fill(0), m2 = Array(n + 2).fill(0);
  for (let epoch = 1; epoch <= EPOCHS; epoch++) {
    const g = Array(n + 2).fill(0), s = Math.exp(w[n + 1]!);
    for (let i = 0; i < train.length; i++) {
      const x = z[i]!; let mu = 0; for (let j = 0; j <= n; j++) mu += x[j]! * w[j]!;
      const [, dmu, dls] = censoredLoss(train[i]!, mu, s);
      for (let j = 0; j <= n; j++) g[j] += dmu * x[j]! / train.length;
      g[n + 1] += dls / train.length;
    }
    for (let j = 0; j < n + 2; j++) {
      if (j > 0 && j <= n) g[j] += .002 * w[j]!;
      m1[j] = .9 * m1[j]! + .1 * g[j]!; m2[j] = .999 * m2[j]! + .001 * g[j]! ** 2;
      w[j] -= .03 * (m1[j]! / (1 - .9 ** epoch)) / (Math.sqrt(m2[j]! / (1 - .999 ** epoch)) + 1e-8);
    }
    w[n + 1] = Math.max(Math.log(.5), Math.min(Math.log(30), w[n + 1]!));
  }
  return { means, scales, weights: w.slice(0, n + 1), sigma: Math.exp(w[n + 1]!) };
}

/** The pre-v2 Scoutroom copy: median winning bid per letter and mechanism. */
function medianBaseline(train: BidRow[]) {
  const median = (xs: number[]) => xs.length ? [...xs].sort((a, b) => a - b)[Math.floor((xs.length - 1) / 2)]! : null;
  const wins = train.filter(r => r.won && r.sample === 0);
  const key = (fp: boolean, l: string) => `${fp}|${l}`, perLetter = new Map<string, number[]>(), perMech = new Map<boolean, number[]>();
  for (const r of wins) { (perLetter.get(key(r.firstPrice, r.letter)) ?? perLetter.set(key(r.firstPrice, r.letter), []).get(key(r.firstPrice, r.letter))!).push(r.top); (perMech.get(r.firstPrice) ?? perMech.set(r.firstPrice, []).get(r.firstPrice)!).push(r.top); }
  return (r: BidRow) => {
    const letter = perLetter.get(key(r.firstPrice, r.letter)) ?? [], mech = perMech.get(r.firstPrice) ?? [];
    const p50 = letter.length >= 5 ? median(letter) : mech.length >= 10 ? median(mech) : LIVE_WINNING_BID[r.letter.charCodeAt(0) - 65]!;
    const cap = r.firstPrice ? Math.max(0, ...r.rivals) + 1 : Infinity;
    return Math.max(0, Math.min(r.balance, Math.round(p50!), cap));
  };
}

/** predict: unconditional bid. givenWin: its best guess of the bid once told the runner-up price. */
function scoreBids(test: BidRow[], predict: (r: BidRow) => number, givenWin: (r: BidRow, floor: number) => number) {
  let absErr = 0, exact = 0, agree = 0, decidable = 0;
  for (const r of test) {
    const bid = predict(r);
    if (r.won && r.top < r.balance) { absErr += Math.abs(Math.min(r.balance, givenWin(r, r.firstPrice ? 0 : r.paid)) - r.top); exact++; }
    // Outcome is decidable when the rival maximum is public: every loss, and Vickrey wins (paid = runner-up).
    if (!r.won) { decidable++; if (bid <= r.top) agree++; }
    else if (!r.firstPrice && r.paid > 1) { decidable++; if (bid >= r.paid) agree++; }
  }
  return { mae: exact ? absErr / exact : null, agreement: decidable ? agree / decidable : null, exact };
}

function validate(bids: BidRow[], words: WordRow[], ids: number[]): CloneValidation {
  const cut = ids[Math.max(0, Math.floor(ids.length * (1 - TEST_SHARE)) - 1)]!;
  const trainB = bids.filter(r => r.match <= cut), trainW = words.filter(r => r.match <= cut);
  const testB = bids.filter(r => r.match > cut && r.sample === 0 && r.left > 0 && r.balance > 0), testW = words.filter(r => r.match > cut && r.sample === 0);
  const style = fitStyle(trainB, trainW), fit = fitBid(trainB, style);
  const model = { style, bid: { features: CLONE_FEATURE_SET, ...fit } };
  const cloneBid = (r: BidRow) => {
    const v = asView(r), mu = predictCloneBid(model, v);
    return Math.max(0, Math.min(r.balance, Math.round(r.firstPrice ? Math.min(mu, Math.max(0, ...r.rivals) + 1) : mu)));
  };
  // Truncated-normal mean: E[bid | bid >= runner-up price].
  const cloneGivenWin = (r: BidRow, floor: number) => {
    const mu = predictCloneBid(model, asView(r)), s = fit.sigma, a = (floor - mu) / s;
    return mu + s * (.3989422804014327 * Math.exp(-a * a / 2)) / (1 - cdf(a));
  };
  const baseline = medianBaseline(trainB);
  const clone = scoreBids(testB, cloneBid, cloneGivenWin), base = scoreBids(testB, baseline, (r, floor) => Math.max(baseline(r), floor));
  const wordHits = testW.filter(r => { const w = chooseImitationWord(asView(r), style); return w && wordReward(w) === r.reward; }).length;
  const posT = testW.map(r => ({ ...r, best: r.best ?? bestByLength(r.rack) })), negT = testB.map(r => ({ ...r, best: r.best ?? bestByLength(r.rack) }));
  const tpr = posT.length ? posT.filter(r => playsNow(style, r)).length / posT.length : null;
  const tnr = negT.length ? negT.filter(r => !playsNow(style, r)).length / negT.length : null;
  return {
    trainMatches: ids.filter(id => id <= cut).length, testMatches: ids.filter(id => id > cut).length, testBids: clone.exact, testWords: testW.length,
    bidMAE: clone.mae, baselineBidMAE: base.mae, outcomeAgreement: clone.agreement, baselineOutcomeAgreement: base.agreement,
    wordAgreement: testW.length ? wordHits / testW.length : null, playTimingAccuracy: tpr !== null && tnr !== null ? (tpr + tnr) / 2 : null,
  };
}

export function fitClone(profile: Raw, cache: Record<string, Raw>, snapshotAt: string): CloneModel {
  const began = performance.now();
  const { bids, words, skipped } = observe(profile.matchIds, cache, profile.botId);
  const ids = [...new Set(bids.map(r => r.match))].sort((a, b) => a - b);
  if (ids.length < MIN_MATCHES) throw Error(`${profile.name}: only ${ids.length} replayable matches (need ${MIN_MATCHES}). Refresh scouting or pick another bot.`);
  const validation = validate(bids, words, ids);
  const style = fitStyle(bids, words), bid = fitBid(bids, style);
  const model: CloneModel = {
    schemaVersion: 2, kind: 'clone',
    source: { botId: profile.botId, name: profile.name, rank: profile.rank, rating: profile.rating, snapshotAt, matchIds: ids, latestMatchEndedAt: profile.latestMatchEndedAt ?? null },
    style, bid: { features: CLONE_FEATURE_SET, ...bid }, validation,
    evidence: { usableMatches: ids.length, skippedMatches: skipped.length, rackSamples: RACK_SAMPLES, trainingRows: bids.length },
    fittedAt: new Date().toISOString(), fitSeconds: (performance.now() - began) / 1000,
  };
  validateCloneModel(model);
  return model;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const arg = (flag: string) => { const i = process.argv.indexOf(flag); return i > 0 ? process.argv[i + 1] : undefined; };
  const botId = Number(arg('--bot')), out = arg('--out');
  if (!Number.isSafeInteger(botId) || !out) { console.error('usage: clone-engine.mts --bot <botId> --out <model.json>'); process.exit(2); }
  const dir = fileURLToPath(new URL('../results/scouting/', import.meta.url));
  const snapshot = JSON.parse(readFileSync(dir + 'profiles.json', 'utf8'));
  const profile = snapshot.profiles.find((p: Raw) => p.botId === botId);
  if (!profile) { console.error(`Bot ${botId} is not in the current scouting snapshot`); process.exit(3); }
  const cache = JSON.parse(readFileSync(dir + 'matches.json', 'utf8')).matches;
  try {
    const model = fitClone(profile, cache, snapshot.generatedAt);
    writeFileSync(out + '.tmp', JSON.stringify(model, null, 2) + '\n'); renameSync(out + '.tmp', out);
    console.log(JSON.stringify({ source: profile.name, style: model.style, sigma: model.bid.sigma, validation: model.validation, evidence: model.evidence, seconds: model.fitSeconds.toFixed(1) }));
  } catch (e) { console.error(e instanceof Error ? e.message : e); process.exit(1); }
}
