// Public, read-only, finished-match archive fetch. No credential or live bids.
import { writeFileSync, mkdirSync } from 'node:fs';
import { sql } from './sql.mjs';
const count = Number(process.argv[2] ?? 20), hero = Number(process.argv[3] ?? 208);
if (!Number.isInteger(count) || count < 1 || count > 100 || !Number.isSafeInteger(hero)) throw new Error('Invalid count/bot id');
const mine = (await sql(`SELECT * FROM match_participant WHERE bot_id = ${hero}`)).sort((a,b) => Number(b.match_id)-Number(a.match_id)).slice(0, count + 10);
if (!mine.length) throw new Error('No match history');
const minimum = Math.min(...mine.map(r => Number(r.match_id)));
const states = await sql(`SELECT * FROM match_state WHERE id >= ${minimum}`);
const selected = states.filter(m => mine.some(p => Number(p.match_id) === Number(m.id)) && Array.isArray(m.status) && m.status[0] === 2)
  .sort((a,b) => Number(b.id)-Number(a.id)).slice(0,count);
const matches: unknown[] = [];
let next = 0;
async function worker() {
  while (next < selected.length) {
    const state = selected[next++]!, id = Number(state.id);
    const [auctions, tops, plays, participants] = await Promise.all([
      sql(`SELECT * FROM auction_result WHERE match_id = ${id}`),
      sql(`SELECT * FROM auction_top_bid_archive WHERE match_id = ${id}`),
      sql(`SELECT * FROM word_play WHERE match_id = ${id}`),
      sql(`SELECT * FROM match_participant WHERE match_id = ${id}`),
    ]);
    matches.push({ state, auctions, tops, plays, participants });
    console.log(`fetched ${matches.length}/${selected.length}: match ${id}, ${auctions.length} auctions, ${tops.length} archived winning bids`);
  }
}
await Promise.all([worker(), worker()]);
mkdirSync('bench/results/viability', { recursive: true });
writeFileSync(process.env.REPLAY_INPUT_OUT ?? 'bench/results/viability/live-replay-input.json', JSON.stringify({ fetchedAt: new Date().toISOString(), hero, matches }, null, 2)+'\n');
