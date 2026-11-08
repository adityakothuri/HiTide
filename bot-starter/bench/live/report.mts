// Live results for one bot: each finished match with its place, score and
// the table, plus running totals.
//   npx tsx bench/live/report.mts <botId> [sinceMatchId]

import { sql } from "./sql.mjs";

const BOT = Number(process.argv[2] ?? 208);
const SINCE = Number(process.argv[3] ?? 0);

const bots = new Map((await sql("SELECT * FROM bot")).map((b) => [Number(b.id), String(b.name)]));
const mine = (await sql(`SELECT * FROM match_participant WHERE bot_id = ${BOT}`))
  .map((p) => Number(p.match_id))
  .filter((m) => m > SINCE)
  .sort((a, b) => a - b);
if (mine.length === 0) {
  console.log(`no matches yet for ${bots.get(BOT) ?? BOT}`);
  process.exit(0);
}
const states = new Map((await sql(`SELECT * FROM match_state WHERE id >= ${mine[0]}`)).map((m) => [Number(m.id), m]));
const parts = await sql(`SELECT * FROM match_participant WHERE match_id >= ${mine[0]}`);

let n = 0, placeSum = 0, wins = 0, scoreSum = 0;
const vsTop = new Map<string, { met: number; beat: number }>();
console.log(`| Match | Place | Score | Table (score) |`);
console.log(`|---:|---:|---:|---|`);
for (const m of mine) {
  const st = states.get(m);
  const ended = Array.isArray(st?.status) && st!.status[0] === 2;
  const table = parts.filter((p) => Number(p.match_id) === m).sort((a, b) => Number(b.score) - Number(a.score));
  const me = table.find((p) => Number(p.bot_id) === BOT)!;
  const place = table.filter((p) => Number(p.score) > Number(me.score)).length + 1;
  const others = table.filter((p) => p !== me).map((p) => `${bots.get(Number(p.bot_id)) ?? p.bot_id} (${p.score})`).join(", ");
  console.log(`| ${m}${ended ? "" : " (live)"} | ${ended ? place : "-"} | ${me.score} | ${others} |`);
  if (!ended) continue;
  n++; placeSum += place; scoreSum += Number(me.score); if (place === 1) wins++;
  for (const p of table) {
    if (p === me) continue;
    const name = bots.get(Number(p.bot_id)) ?? String(p.bot_id);
    const r = vsTop.get(name) ?? { met: 0, beat: 0 };
    r.met++;
    if (Number(me.score) > Number(p.score)) r.beat++;
    vsTop.set(name, r);
  }
}
if (n > 0) {
  console.log(`\n${n} finished: mean place ${(placeSum / n).toFixed(2)}, wins ${wins} (${((100 * wins) / n).toFixed(0)}%), mean score ${(scoreSum / n).toFixed(1)}`);
  console.log("Head-to-head (finished above them / met):");
  console.log([...vsTop.entries()].sort((a, b) => b[1].met - a[1].met).map(([k, v]) => `${k} ${v.beat}/${v.met}`).join(", "));
}
