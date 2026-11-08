// Print the live leaderboard: real (non-simulated) bots by rating.
//   npx tsx bench/live/leaderboard.ts [limit]

import { sql } from "./sql.mjs";

const LIMIT = Number(process.argv[2] ?? 25);

const bots = new Map((await sql("SELECT * FROM bot")).map((b) => [String(b.id), b]));
const stats = await sql("SELECT * FROM bot_stats");

const rows = stats
  .map((s) => ({ s, b: bots.get(String(s.bot_id)) }))
  .filter(({ b }) => b && !b.is_simulated)
  .sort((x, y) => Number(y.s.rating) - Number(x.s.rating));

console.log(`${rows.length} real bots with stats (of ${bots.size} bots)\n`);
console.log("| # | Bot (id) | Rating | Matches | Wins | Win % | Avg score |");
console.log("|---:|---|---:|---:|---:|---:|---:|");
for (const [i, { s, b }] of rows.slice(0, LIMIT).entries()) {
  const m = Number(s.matches_played);
  console.log(
    `| ${i + 1} | ${b!.name} (${s.bot_id}) | ${s.rating} | ${m} | ${s.wins} | ${m ? ((100 * Number(s.wins)) / m).toFixed(0) : "-"}% | ${m ? (Number(s.total_score) / m).toFixed(0) : "-"} |`,
  );
}
const sims = stats.filter((s) => bots.get(String(s.bot_id))?.is_simulated);
console.log("\nSimulated bots:");
for (const s of sims) {
  const m = Number(s.matches_played);
  console.log(`  ${bots.get(String(s.bot_id))!.name}: rating ${s.rating}, ${m} matches, avg score ${m ? (Number(s.total_score) / m).toFixed(0) : "-"}`);
}
