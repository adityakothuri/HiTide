// Read-only market analysis: npx tsx bench/live/market.mts [matches=400]
// Writes bench/results/live-market.json when run.
import * as fs from "node:fs";
import { sql } from "./sql.mjs";

const MATCHES = Number(process.argv[2] ?? 400);
if (!Number.isSafeInteger(MATCHES) || MATCHES < 1) throw new Error("matches must be a positive integer");
const opt = (v: unknown): number | null => Array.isArray(v) && v[0] === 0 ? Number(v[1]) : null;
const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const face = [1, 3, 3, 2, 1, 4, 2, 4, 1, 8, 5, 1, 3, 1, 1, 3, 10, 1, 1, 1, 1, 4, 4, 8, 4, 10];
const mean = (xs: number[]): number | null => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
// Linearly interpolated percentiles, including the conventional even-sample median.
const percentile = (xs: number[], p: number): number | null => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b), index = (s.length - 1) * p;
  const lo = Math.floor(index), hi = Math.ceil(index);
  return s[lo]! + (s[hi]! - s[lo]!) * (index - lo);
};
const fmt = (n: number | null) => n === null ? "—" : n.toFixed(2);
const pct = (n: number | null) => n === null ? "—" : `${(100 * n).toFixed(1)}%`;
const table = (headers: string[], rows: (string | number)[][]) => {
  console.log(`| ${headers.join(" | ")} |`);
  console.log(`| ${headers.map((_, i) => i ? "---:" : "---").join(" | ")} |`);
  for (const row of rows) console.log(`| ${row.join(" | ")} |`);
  console.log();
};

// Filter all match states before limiting so sparse finished matches are not missed.
const matches = (await sql("SELECT * FROM match_state"))
  .filter((m) => Array.isArray(m.status) && m.status[0] === 2)
  .sort((a, b) => Number(b.id) - Number(a.id)).slice(0, MATCHES);
const ids = new Set(matches.map((m) => Number(m.id)));
const minId = ids.size ? Math.min(...ids) : null;
const selected = async (tableName: string) => minId === null ? [] :
  (await sql(`SELECT * FROM ${tableName} WHERE match_id >= ${minId}`)).filter((r) => ids.has(Number(r.match_id)));
const [results, archive, parts, bots] = await Promise.all([
  selected("auction_result"), selected("auction_top_bid_archive"), selected("match_participant"),
  ids.size ? sql("SELECT * FROM bot") : Promise.resolve([]),
]);
const key = (m: unknown, a: unknown) => `${m}:${a}`;
const tops = new Map(archive.map((r) => [key(r.match_id, r.auction_id), Number(r.top_bid)]));
const simulated = new Set(bots.filter((b) => b.is_simulated === true).map((b) => Number(b.id)));
interface Bucket {
  auctions: number; unsold: number; simulatedWins: number;
  topBids: number[]; pricesPaid: number[]; gaps: number[];
}
const bucket = (): Bucket => ({ auctions: 0, unsold: 0, simulatedWins: 0, topBids: [], pricesPaid: [], gaps: [] });
const perLetter = Object.fromEntries([...letters].map((l) => [l, bucket()]));
const perPhase = Array.from({ length: 7 }, bucket);
const groups: Record<string, number[]> = { Vowels: [], Consonants: [], "High-value (face ≥ 4)": [] };
const totals = new Map(matches.map((m) => [Number(m.id), { matchId: Number(m.id), totalSpend: 0, totalScore: 0 }]));
const byMatch = new Map<number, typeof results>();
for (const r of results) {
  const id = Number(r.match_id);
  const rows = byMatch.get(id) ?? [];
  rows.push(r);
  byMatch.set(id, rows);
}
for (const [id, rows] of byMatch) {
  rows.sort((a, b) => Number(a.auction_id) - Number(b.auction_id));
  for (const [i, r] of rows.entries()) {
    const letter = String(r.letter).toUpperCase(), winner = opt(r.winner_bot_id);
    const paid = Number(r.paid), top = tops.get(key(id, r.auction_id));
    // Seven equal-order ranges (~10 auctions each for a 70-auction match).
    const phase = perPhase[Math.floor(i * 7 / rows.length)]!;
    for (const b of [perLetter[letter], phase]) {
      if (!b) continue;
      b.auctions++;
      if (winner === null) { b.unsold++; continue; }
      b.pricesPaid.push(paid);
      if (simulated.has(winner)) b.simulatedWins++;
      // Missing archive entries stay missing; the paid price is not a top bid.
      if (top !== undefined) { b.topBids.push(top); b.gaps.push(top - paid); }
    }
    if (winner === null) continue;
    totals.get(id)!.totalSpend += paid;
    if (letters.includes(letter) && letter.length === 1) {
      groups["AEIOU".includes(letter) ? "Vowels" : "Consonants"]!.push(paid);
      if (face[letters.indexOf(letter)]! >= 4) groups["High-value (face ≥ 4)"]!.push(paid);
    }
  }
}
for (const p of parts) totals.get(Number(p.match_id))!.totalScore += Number(p.score);
const summarize = (b: Bucket) => ({
  ...b, sold: b.auctions - b.unsold,
  missingTopBids: b.pricesPaid.length - b.topBids.length,
  unsoldShare: b.auctions ? b.unsold / b.auctions : null,
  meanTopBid: mean(b.topBids), medianTopBid: percentile(b.topBids, 0.5),
  meanPaid: mean(b.pricesPaid), medianPaid: percentile(b.pricesPaid, 0.5), meanGap: mean(b.gaps),
  simulatedWinShare: b.auctions ? b.simulatedWins / b.auctions : null,
});
const letterStats = Object.fromEntries(Object.entries(perLetter).map(([l, b]) => [l, summarize(b)]));
const phaseStats = perPhase.map((b, i) => ({ phase: i + 1, ...summarize(b) }));
const matchStats = [...totals.values()];
const vickrey = matches.filter((m) => Array.isArray(m.auction_type) && m.auction_type[0] === 1).length;
console.log(`${matches.length} most recent finished matches; ${vickrey} Vickrey.\n`);
console.log("Bid/price statistics and percentiles cover sold auctions only; paid is the second-highest bid in Vickrey.");
console.log("Missing archived top bids are excluded from top/gap statistics. Simulated-win share uses all auctions.\n");
table(["Letter", "Auctions", "Unsold", "Mean top", "Median top", "Mean paid", "Median paid", "Mean top−paid", "Missing tops"],
  Object.entries(letterStats).map(([l, b]) => [l, b.auctions, pct(b.unsoldShare), fmt(b.meanTopBid),
    fmt(b.medianTopBid), fmt(b.meanPaid), fmt(b.medianPaid), fmt(b.meanGap), b.missingTopBids]));
console.log("Phases split each match into seven roughly equal ranges by auction_id order.\n");
table(["Phase", "Auctions", "Mean top", "Mean paid", "Simulated wins / auctions", "Missing tops"],
  phaseStats.map((b) => [b.phase, b.auctions, fmt(b.meanTopBid), fmt(b.meanPaid), pct(b.simulatedWinShare), b.missingTopBids]));
table(["Paid-price group", "Sold auctions", "P10", "P25", "P50", "P75", "P90"],
  Object.entries(groups).map(([name, xs]) => [name, xs.length, ...[0.1, 0.25, 0.5, 0.75, 0.9].map((p) => fmt(percentile(xs, p)))]));
table(["Match", "Total spend", "Total final score"], matchStats.map((m) => [m.matchId, m.totalSpend, m.totalScore]));
const spends = matchStats.map((m) => m.totalSpend), scores = matchStats.map((m) => m.totalScore);
table(["Across matches", "Total spend", "Total final score"], [
  ["Mean", fmt(mean(spends)), fmt(mean(scores))],
  ["Median", fmt(percentile(spends, 0.5)), fmt(percentile(scores, 0.5))],
]);
fs.mkdirSync(new URL("../results/", import.meta.url), { recursive: true });
fs.writeFileSync(new URL("../results/live-market.json", import.meta.url), JSON.stringify({
  requestedMatches: MATCHES, matches: matches.length, vickreyMatches: vickrey,
  conventions: { prices: "sold auctions", topBids: "sold auctions with archived top bid", simulatedWinDenominator: "all auctions", percentile: "linear interpolation" },
  perLetter: letterStats, perPhase: phaseStats, priceGroups: groups, perMatch: matchStats,
}, null, 2));
