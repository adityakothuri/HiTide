// Reproducible viability test. Uses server timing (no final-tile cash-in),
// hidden five-tile starting racks, and only public information for policies.
import { writeFileSync } from 'node:fs';
import { Lexicon, SLOT_VALUE, slotOf } from './lexicon.js';
import type { Policy } from './policy.js';
import { portfolio, PARAMS, TUNED_PARAMS } from './strategies/portfolio.js';
import { starter } from './strategies/baselines.js';
import { planner } from './strategies/planner.js';
import { CHOICES } from './strategy.js';
import { runMatch, mulberry32, type Seat } from './sim.js';

const games = Number(process.env.EVAL_GAMES ?? 200);
const seed = Number(process.env.EVAL_SEED ?? 710001);
if (!Number.isInteger(games) || games < 2) throw new Error('EVAL_GAMES must be >= 2');
const started = performance.now();
const lexicon = Lexicon.fromFile(new URL('../../spacetimedb/wordlist.txt', import.meta.url));
const startupMs = performance.now() - started;
const greedy: Policy = {
  name: 'GreedyShortBot', bid: v => Math.min(v.balance, SLOT_VALUE[slotOf(v.letter)]! * 2),
  play(v) { const i = v.lexicon.best(v.rack, 2); return i < 0 ? null : v.lexicon.words[i]!; },
};
const hoarder: Policy = {
  name: 'BlindHoarderBot', bid: v => Math.min(v.balance, SLOT_VALUE[slotOf(v.letter)]! * 3 + 4),
  play(v) { const i = v.lexicon.best(v.rack, 7); return i < 0 ? null : v.lexicon.words[i]!; },
};
const heuristic = planner({ pointsToBid: 3, faceFloor: 3, flatFloor: 3, maxBidShare: 0.8 }, 'HeuristicVickreyBot');
const fields: Record<string, Policy[]> = {
  requested: [{ ...starter, name: 'StarterBot' }, greedy, hoarder, heuristic, CHOICES.final!()],
  strong: [CHOICES.final!(), CHOICES.l1!(), CHOICES.ha2!(), CHOICES.marketps!(), heuristic],
};
const latencies: Record<string, number[]> = { bid: [], play: [] };
const overrides = { ...(process.env.EVAL_VARIANT === 'tuned' ? TUNED_PARAMS : {}), ...JSON.parse(process.env.EVAL_PARAMS ?? '{}') } as Partial<typeof PARAMS>;
const candidate = portfolio(overrides);
const hero: Policy = {
  name: candidate.name,
  bid(v) { const t = performance.now(); const out = candidate.bid(v); latencies.bid!.push(performance.now() - t); return out; },
  play(v) { const t = performance.now(); const out = candidate.play(v); latencies.play!.push(performance.now() - t); return out; },
};
function stats(xs: number[], z = 1.96) {
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  const variance = xs.reduce((a, b) => a + (b - mean) ** 2, 0) / (xs.length - 1);
  const half = z * Math.sqrt(variance / xs.length);
  return { mean, ci: [mean - half, mean + half] };
}
function winStats(xs: number[]) {
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length, n = xs.length, z = 1.96;
  const center = (mean + z * z / (2 * n)) / (1 + z * z / n);
  const half = z * Math.sqrt(mean * (1 - mean) / n + z * z / (4 * n * n)) / (1 + z * z / n);
  return { mean, ci: [Math.max(0, center - half), Math.min(1, center + half)] };
}
const reports = [];
for (const firstPrice of [false, true]) {
  for (const [field, opponents] of Object.entries(fields)) {
    const policies = [hero, ...opponents];
    const scores = policies.map(() => [] as number[]), wins = policies.map(() => [] as number[]);
    const places = policies.map(() => [] as number[]);
    for (let game = 0; game < games; game++) {
      // Rotate seats to remove fixed deal-position preference. Disjoint seeds
      // across fields and auction mechanisms; seeds are fixed before testing.
      const rotation = game % 6;
      const seats: Seat[] = policies.map(policy => ({ kind: 'policy', policy }));
      const rotated = [...seats.slice(rotation), ...seats.slice(0, rotation)];
      const out = runMatch(rotated, mulberry32(seed + game + (firstPrice ? 100000 : 0) + (field === 'strong' ? 200000 : 0)),
        { lexicon, firstPrice, startingRack: 5, startingBalance: 100 });
      const top = Math.max(...out.map(r => r.score)), tied = out.filter(r => r.score === top).length;
      out.forEach((r, i) => {
        const original = (i + rotation) % 6;
        scores[original]!.push(r.score);
        wins[original]!.push(r.score === top ? 1 / tied : 0);
        places[original]!.push(r.place + 1);
      });
    }
    const rows = policies.map((p, i) => ({ name: p.name, score: stats(scores[i]!), winShare: winStats(wins[i]!), place: stats(places[i]!) }));
    // 3.25 is a conservative normal critical value for 40 comparisons
    // (5 opponents * 2 metrics * 4 cells), Bonferroni family alpha < .05.
    // Approximate sampling intervals, not a guarantee over arbitrary opponents.
    const comparisons = opponents.map((p, j) => {
      const scoreDifference = stats(scores[0]!.map((x, g) => x - scores[j + 1]![g]!), 3.25);
      const winDifference = stats(wins[0]!.map((x, g) => x - wins[j + 1]![g]!), 3.25);
      // Distribution-free Hoeffding interval for paired win-share difference
      // in [-1,1]; family-adjusted across all 40 score/win comparisons.
      const half = Math.sqrt(2 * Math.log(2 * 40 / .05) / games);
      winDifference.ci = [Math.max(-1, winDifference.mean - half), Math.min(1, winDifference.mean + half)];
      return { opponent: p.name, scoreDifference, winDifference };
    });
    const report = { mode: firstPrice ? 'FirstPrice' : 'Vickrey', field, games, rows, comparisons,
      superioritySupported: comparisons.every(c => c.scoreDifference.ci[0]! > 0 && c.winDifference.ci[0]! > 0) };
    reports.push(report);
    console.log(JSON.stringify(report));
  }
}
const percentile = (xs: number[], q: number) => xs[Math.min(xs.length - 1, Math.floor(q * xs.length))]!;
const timing = Object.fromEntries(Object.entries(latencies).map(([name, xs]) => {
  xs.sort((a, b) => a - b);
  return [name, { calls: xs.length, p50Ms: percentile(xs, .5), p95Ms: percentile(xs, .95), p99Ms: percentile(xs, .99), maxMs: xs.at(-1) }];
}));
const result = { seed, gamesPerCell: games, words: lexicon.words.length, params: { ...PARAMS, ...overrides }, startupMs,
  elapsedSeconds: (performance.now() - started) / 1000, timing, reports };
if (process.env.EVAL_OUT) writeFileSync(process.env.EVAL_OUT, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ ...result, reports: undefined }));
