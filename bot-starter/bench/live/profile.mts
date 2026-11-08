// Profile how live bots play, from public tables of recent finished matches.
//   npx tsx bench/live/profile.ts [matches=400] [botIds comma-separated]
//
// For each bot: average place and score, tiles won per match, what it bid
// on the tiles it won (top bid, from the post-match archive) relative to
// the tile's face value, what it paid, and the length of words it played.
// Writes the raw per-bot numbers to bench/results/live-profile.json.

import * as fs from "node:fs";
import { LETTER_VALUE } from "../../src/lexicon.js";
import { sql } from "./sql.mjs";

const MATCHES = Number(process.argv[2] ?? 400);
const FOCUS = (process.argv[3] ?? "").split(",").filter(Boolean);

const opt = (v: unknown): number | null => {
  // SATS option: [0, value] = some, [1, []] = none
  if (Array.isArray(v) && v[0] === 0) return Number(v[1]);
  return null;
};

const [{ m: maxId }] = (await sql("SELECT * FROM match_state")).reduce(
  (acc, r) => [{ m: Math.max(acc[0]!.m, Number(r.id)) }],
  [{ m: 0 }],
);
const from = maxId - MATCHES * 2; // over-fetch; keep only finished ones
const matches = (await sql(`SELECT * FROM match_state WHERE id > ${from}`))
  .filter((m) => Array.isArray(m.status) && m.status[0] === 2) // Ended
  .sort((a, b) => Number(b.id) - Number(a.id))
  .slice(0, MATCHES);
const ids = new Set(matches.map((m) => Number(m.id)));
const minId = Math.min(...ids);
const vickrey = matches.filter((m) => Array.isArray(m.auction_type) && m.auction_type[0] === 1).length;

const bots = new Map((await sql("SELECT * FROM bot")).map((b) => [Number(b.id), b]));
const parts = (await sql(`SELECT * FROM match_participant WHERE match_id >= ${minId}`)).filter((p) => ids.has(Number(p.match_id)));
const results = (await sql(`SELECT * FROM auction_result WHERE match_id >= ${minId}`)).filter((r) => ids.has(Number(r.match_id)));
const tops = new Map((await sql(`SELECT * FROM auction_top_bid_archive WHERE match_id >= ${minId}`)).map((t) => [Number(t.auction_id), Number(t.top_bid)]));
const plays = (await sql(`SELECT * FROM word_play WHERE match_id >= ${minId}`)).filter((w) => ids.has(Number(w.match_id)));

interface Prof {
  name: string; sim: boolean; matches: number; placeSum: number; scoreSum: number; wins: number;
  tilesWon: number; paidSum: number; topSum: number; faceSum: number;
  overFace: number[]; // top bid minus face value, per tile won
  words: number; lenHist: Record<number, number>; lastAuctionWins: number;
  pairs: [number, number, number][]; // face, top bid, vowel 0/1
}
const prof = new Map<number, Prof>();
const get = (id: number): Prof => {
  let p = prof.get(id);
  if (!p) {
    const b = bots.get(id);
    p = { name: String(b?.name ?? id), sim: Boolean(b?.is_simulated), matches: 0, placeSum: 0, scoreSum: 0, wins: 0,
      tilesWon: 0, paidSum: 0, topSum: 0, faceSum: 0, overFace: [], words: 0, lenHist: {}, lastAuctionWins: 0, pairs: [] };
    prof.set(id, p);
  }
  return p;
};

const byMatch = new Map<number, typeof parts>();
for (const p of parts) {
  const m = Number(p.match_id);
  byMatch.set(m, [...(byMatch.get(m) ?? []), p]);
}
let tableSizes = 0;
for (const [, ps] of byMatch) {
  tableSizes += ps.length;
  for (const p of ps) {
    const me = get(Number(p.bot_id));
    const place = ps.filter((q) => Number(q.score) > Number(p.score)).length;
    me.matches++;
    me.placeSum += place + 1;
    me.scoreSum += Number(p.score);
    if (place === 0) me.wins++;
  }
}

const lastAuction = new Map<number, number>();
for (const r of results) {
  const m = Number(r.match_id);
  lastAuction.set(m, Math.max(lastAuction.get(m) ?? 0, Number(r.auction_id)));
}
let marketTop = 0, marketPaid = 0, marketN = 0, unsold = 0;
for (const r of results) {
  const w = opt(r.winner_bot_id);
  if (w === null) { unsold++; continue; }
  const me = get(w);
  const face = LETTER_VALUE[String(r.letter)] ?? 0;
  const top = tops.get(Number(r.auction_id)) ?? Number(r.paid);
  me.tilesWon++;
  me.paidSum += Number(r.paid);
  me.topSum += top;
  me.faceSum += face;
  me.overFace.push(top - face);
  me.pairs.push([face, top, "AEIOU".includes(String(r.letter)) ? 1 : 0]);
  if (Number(r.auction_id) === lastAuction.get(Number(r.match_id))) me.lastAuctionWins++;
  marketTop += top; marketPaid += Number(r.paid); marketN++;
}
for (const w of plays) {
  const me = get(Number(w.bot_id));
  const len = String(w.word).length;
  me.words++;
  me.lenHist[len] = (me.lenHist[len] ?? 0) + 1;
}

const median = (xs: number[]) => {
  if (xs.length === 0) return NaN;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)]!;
};

console.log(`${matches.length} finished matches (ids ${minId}..${Math.max(...ids)}), ${vickrey} Vickrey, avg table ${(tableSizes / byMatch.size).toFixed(1)} bots`);
console.log(`auctions: ${results.length} (${unsold} unsold); sold tiles: mean top bid ${(marketTop / marketN).toFixed(1)}, mean paid ${(marketPaid / marketN).toFixed(1)}\n`);
console.log("| Bot | Matches | Avg place | Win % | Avg score | Tiles won/match | Avg top bid | Avg paid | Median bid−face | Words/match | Avg word len | 7+ share | Last-auction wins |");
console.log("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|");
const list = [...prof.entries()]
  .filter(([id, p]) => p.matches >= 10 && (FOCUS.length === 0 || FOCUS.includes(String(id))))
  .sort((a, b) => a[1].placeSum / a[1].matches - b[1].placeSum / b[1].matches);
for (const [id, p] of list.slice(0, 30)) {
  const lens = Object.entries(p.lenHist);
  const totalLen = lens.reduce((a, [l, n]) => a + Number(l) * n, 0);
  const long = lens.filter(([l]) => Number(l) >= 7).reduce((a, [, n]) => a + n, 0);
  console.log(`| ${p.name}${p.sim ? " (sim)" : ""} (${id}) | ${p.matches} | ${(p.placeSum / p.matches).toFixed(2)} | ${((100 * p.wins) / p.matches).toFixed(0)}% | ${(p.scoreSum / p.matches).toFixed(0)} | ${(p.tilesWon / p.matches).toFixed(1)} | ${p.tilesWon ? (p.topSum / p.tilesWon).toFixed(1) : "-"} | ${p.tilesWon ? (p.paidSum / p.tilesWon).toFixed(1) : "-"} | ${median(p.overFace)} | ${(p.words / p.matches).toFixed(1)} | ${p.words ? (totalLen / p.words).toFixed(1) : "-"} | ${p.words ? ((100 * long) / p.words).toFixed(0) : "-"}% | ${p.lastAuctionWins} |`);
}

fs.mkdirSync(new URL("../results/", import.meta.url), { recursive: true });
fs.writeFileSync(new URL("../results/live-profile.json", import.meta.url), JSON.stringify(Object.fromEntries(prof), null, 1));

// Least-squares fit per bot: top bid ~ a*face + b + c*vowel.
function fit(pairs: [number, number, number][]) {
  // normal equations for 3 params
  const X = pairs.map(([f, , v]) => [f, 1, v]);
  const y = pairs.map(([, t]) => t);
  const XtX = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  const Xty = [0, 0, 0];
  for (let i = 0; i < X.length; i++) for (let j = 0; j < 3; j++) {
    Xty[j]! += X[i]![j]! * y[i]!;
    for (let k = 0; k < 3; k++) XtX[j]![k]! += X[i]![j]! * X[i]![k]!;
  }
  // solve 3x3 by Cramer
  const det = (m: number[][]) => m[0]![0]! * (m[1]![1]! * m[2]![2]! - m[1]![2]! * m[2]![1]!) - m[0]![1]! * (m[1]![0]! * m[2]![2]! - m[1]![2]! * m[2]![0]!) + m[0]![2]! * (m[1]![0]! * m[2]![1]! - m[1]![1]! * m[2]![0]!);
  const D = det(XtX);
  const sol = [0, 1, 2].map((c) => det(XtX.map((row, r) => row.map((v, k) => (k === c ? Xty[r]! : v)))) / D);
  const resid = X.map((x, i) => y[i]! - (sol[0]! * x[0]! + sol[1]! + sol[2]! * x[2]!));
  const sd = Math.sqrt(resid.reduce((a, r) => a + r * r, 0) / Math.max(1, resid.length - 3));
  return { a: sol[0]!, b: sol[1]!, c: sol[2]!, sd };
}
console.log("\nBid fits (winning top bid ~ a*face + b + c*vowel), bots with 300+ tiles won:");
console.log("| Bot | tiles | a | b | c (vowel) | resid sd | 7+ word share | words/match |");
console.log("|---|---:|---:|---:|---:|---:|---:|---:|");
for (const [id, p] of list) {
  if (p.pairs.length < 300 || p.sim) continue;
  const f = fit(p.pairs);
  const long = Object.entries(p.lenHist).filter(([l]) => Number(l) >= 7).reduce((a, [, n]) => a + n, 0);
  console.log(`| ${p.name} (${id}) | ${p.pairs.length} | ${f.a.toFixed(2)} | ${f.b.toFixed(2)} | ${f.c.toFixed(2)} | ${f.sd.toFixed(2)} | ${((100 * long) / Math.max(1, p.words)).toFixed(0)}% | ${(p.words / p.matches).toFixed(1)} |`);
}
